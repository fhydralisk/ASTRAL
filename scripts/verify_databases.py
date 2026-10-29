"""Run ORM contracts against three real database drivers in disposable Docker resources.

Build ``astral-web:decoupling-test`` first. Only containers and the network created
by this invocation are removed; existing services and volumes are never touched.
"""

import argparse
import secrets
import subprocess
import time
import uuid


def run(*args, capture=False, check=True):
    return subprocess.run(
        ["docker", *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-image", default="astral-web:decoupling-test")
    args = parser.parse_args()
    suffix = uuid.uuid4().hex[:10]
    network = "astral-db-test-" + suffix
    containers = []
    password = secrets.token_hex(16)
    run("network", "create", "--internal", "--label", "astral.test=true", network, capture=True)
    try:
        for dialect, image, alias, variables, readiness, url in [
            (
                "postgresql",
                "postgres:17-alpine",
                "postgres-test",
                {"POSTGRES_USER": "astral", "POSTGRES_PASSWORD": password, "POSTGRES_DB": "astral"},
                ["pg_isready", "-h", "127.0.0.1", "-U", "astral", "-d", "astral"],
                f"postgresql://astral:{password}@postgres-test:5432/astral",
            ),
            (
                "mysql",
                "mysql:8.4",
                "mysql-test",
                {
                    "MYSQL_ROOT_PASSWORD": password,
                    "MYSQL_USER": "astral",
                    "MYSQL_PASSWORD": password,
                    "MYSQL_DATABASE": "astral",
                },
                [
                    "mysql",
                    "--host=127.0.0.1",
                    "--protocol=TCP",
                    "-uastral",
                    "--password=" + password,
                    "-Dastral",
                    "-e",
                    "SELECT 1",
                ],
                f"mysql://astral:{password}@mysql-test:3306/astral",
            ),
        ]:
            name = f"astral-{dialect}-test-{suffix}"
            parameters = [
                "run",
                "-d",
                "--name",
                name,
                "--label",
                "astral.test=true",
                "--network",
                network,
                "--network-alias",
                alias,
                "--memory",
                "768m",
                "--cpus",
                "1",
            ]
            for key, value in variables.items():
                parameters.extend(["-e", f"{key}={value}"])
            parameters.append(image)
            print(f"Starting isolated {dialect} test server", flush=True)
            run(*parameters, capture=True)
            containers.append(name)
            for _ in range(180):
                if run("exec", name, *readiness, capture=True, check=False).returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError(f"{dialect} did not become ready")
            run(
                "run",
                "--rm",
                "--network",
                network,
                "--memory",
                "1g",
                "--cpus",
                "1",
                "-e",
                f"INTEGRATION_DIALECT={dialect}",
                "-e",
                f"INTEGRATION_DATABASE_URL={url}",
                args.web_image,
                "npx",
                "vitest",
                "run",
                "tests/repository.integration.test.ts",
            )
            print(
                f"{dialect}: migration, uniqueness, ownership query, CAS and rollback passed",
                flush=True,
            )
        run(
            "run",
            "--rm",
            "--network",
            "none",
            "-e",
            "INTEGRATION_DIALECT=sqlite",
            "-e",
            "INTEGRATION_DATABASE_URL=file:/tmp/astral-repository.db",
            args.web_image,
            "npx",
            "vitest",
            "run",
            "tests/repository.integration.test.ts",
        )
        print("All three database contracts passed", flush=True)
    finally:
        for name in containers:
            run("rm", "-f", "-v", name, capture=True, check=False)
        run("network", "rm", network, capture=True, check=False)


if __name__ == "__main__":
    main()
