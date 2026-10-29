"""Scientific workspace operations, independent of HTTP and browser identity."""

from __future__ import annotations
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote, unquote
import numpy as np
import pandas as pd
from ..core import json_value, update_context_data_descriptions
from ..tools.configure_variable_roles import available_variable_context
from .session import SessionStartError
from .base import ServiceError, Download


def plain_result(value):
    return value


def event_batch(manager, after):
    return manager.get_recent_events(after, limit=32)


def stream_download(chunks, *, media_type, headers=None, background=None):
    return Download(
        chunks,
        unquote(
            (headers or {}).get("Content-Disposition", "attachment").split("filename*=UTF-8''")[-1]
        ),
        media_type,
        background or (lambda: None),
    )


def cleanup_callback(function, *args, **kwargs):
    return lambda: function(*args, **kwargs)


def file_download(path, *, filename, media_type, background=None):
    def chunks():
        with open(path, "rb") as stream:
            yield from iter(lambda: stream.read(1024 * 1024), b"")

    return Download(chunks(), filename, media_type, background or (lambda: None))


MAX_UPLOAD = 256 * 1024 * 1024


def build_operations(session):
    def context_preview_groups(context=None):
        with session.lock:
            context = (
                context if context is not None else available_variable_context(session.context)
            )
            axis_names = context.axis_names()
            groups = []
            for axis in axis_names:
                variables = [
                    name
                    for name, dimensions in context.variable_axes.items()
                    if dimensions == (axis,) and context.data[name].ndim == 1
                ]
                if not variables:
                    continue
                groups.append(
                    {
                        "id": f"axis:{axis}",
                        "kind": "axis",
                        "axis": axis,
                        "axes": [axis],
                        "variables": variables,
                        "shape": [len(context.data[axis])],
                    }
                )
            for name, dimensions in context.variable_axes.items():
                value = context.data[name]
                if value.ndim <= 1:
                    continue
                groups.append(
                    {
                        "id": f"variable:{name}",
                        "kind": "relation" if name in context.relation_names else "variable",
                        "variable": name,
                        "axes": list(dimensions),
                        "shape": list(value.shape),
                        "dtype": str(value.dtype),
                    }
                )
            return groups

    def status():
        return plain_result(session.snapshot())

    def capabilities(agent: str = "search"):
        try:
            return session.capabilities(agent)
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc

    def start(payload: dict = None):
        try:
            return session.start(payload)
        except SessionStartError as exc:
            raise ServiceError(
                500,
                {
                    "code": "start_response_failed" if exc.started else "start_preflight_failed",
                    "message": str(exc),
                    "run_id": exc.run_id,
                    "started": exc.started,
                },
            ) from exc
        except (ValueError, OSError) as exc:
            raise ServiceError(400, str(exc)) from exc

    def prepare_data(payload: dict = None):
        try:
            return session.prepare_data(str(payload.get("message", "")))
        except (ValueError, OSError) as exc:
            raise ServiceError(400, str(exc)) from exc

    def data_agent_events(after_seq: int = 0):
        return event_batch(session.data_interaction_manager, max(0, after_seq))

    def stop_data_preparation():
        try:
            return session.stop_data_preparation()
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc

    def configure_data_agent(payload: dict = None):
        try:
            return session.configure_data_agent(payload)
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc

    def test_data_agent_model(payload: dict = None):
        try:
            return session.test_data_agent_model(payload)
        except Exception as exc:
            raise ServiceError(400, str(exc)) from exc

    def test_model(payload: dict = None):
        try:
            return session.test_model(payload)
        except Exception as exc:
            raise ServiceError(400, str(exc)) from exc

    def evaluator_configuration(selected: str | None = None):
        try:
            return session.evaluator_configuration(selected)
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc

    def configure_evaluator(payload: dict = None):
        try:
            return session.configure_evaluator(payload)
        except (TypeError, ValueError) as exc:
            raise ServiceError(400, str(exc)) from exc

    def test_evaluator(payload: dict = None):
        try:
            return session.test_evaluator(payload)
        except Exception as exc:
            raise ServiceError(400, str(exc)) from exc

    def start_evaluator_assistance(payload: dict = None):
        try:
            return session.start_evaluator_assistance(payload)
        except (OSError, ValueError) as exc:
            raise ServiceError(400, str(exc)) from exc

    def evaluator_agent_events(after_seq: int = 0):
        return event_batch(session.evaluator_interaction_manager, max(0, after_seq))

    def stop_evaluator_assistance():
        try:
            return session.stop_evaluator_assistance()
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc

    def configure_evaluator_agent(payload: dict = None):
        try:
            return session.configure_evaluator_agent(payload)
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc

    def test_evaluator_agent_model(payload: dict = None):
        try:
            return session.test_evaluator_agent_model(payload)
        except Exception as exc:
            raise ServiceError(400, str(exc)) from exc

    def data_context(rows: int = 300):
        rows = max(1, min(rows, 1000))
        with session.lock:
            context = available_variable_context(session.context)
            schema = {**context.schema(), "features": list(session.context.feature_names())}
            all_axis_names = set(context.axis_names())
            groups = {}
            for name, value in context.data.items():
                if name in all_axis_names or value.ndim != 1:
                    continue
                key = tuple(context.variable_axes.get(name, (f"length:{len(value)}",)))
                groups.setdefault(key, []).append(name)
            preferred = next((names for names in groups.values() if context.target in names), None)
            names = preferred or max(
                groups.values(), key=lambda item: (len(item), item), default=[]
            )
            total = len(context.data[names[0]]) if names else 0
            referenced_axes = list(
                dict.fromkeys(
                    (axis for name in names for axis in context.variable_axes.get(name, ()))
                )
            )
            matching_axes = [name for name in all_axis_names if len(context.data[name]) == total]
            axis_names = [name for name in referenced_axes if name in matching_axes] + [
                name for name in matching_axes if name not in referenced_axes
            ]
            preview_columns = [*axis_names, *names]
            columns = [
                *context.axis_names(),
                *(name for name in context.data if name not in all_axis_names),
            ]
            arrays = {
                **{name: context.data[name] for name in axis_names},
                **{name: context.data[name] for name in names},
            }
            count = min(total, rows)
            records = [
                {name: json_value(arrays[name][index]) for name in preview_columns}
                for index in range(count)
            ]
            descriptions = {
                name: context.variable_descriptions.get(name, "") for name in context.data
            }
        return {
            **json_value(schema),
            "preview_groups": context_preview_groups(context),
            "columns": columns,
            "preview_columns": preview_columns,
            "column_kinds": {
                **{name: "axis" for name in all_axis_names},
                **{name: "variable" for name in context.data if name not in all_axis_names},
            },
            "rows": total,
            "variable_descriptions": descriptions,
            "data": records,
            "truncated": total > count,
        }

    def data_context_preview(group: str, limit: int = 100):
        limit = max(1, min(limit, 300))
        with session.lock:
            context = available_variable_context(session.context)
            groups = {item["id"]: item for item in context_preview_groups(context)}
            selected = groups.get(group)
            if selected is None:
                raise ServiceError(404, "Unknown context data preview group")
            if selected["kind"] == "axis":
                axis = selected["axis"]
                columns = [axis, *selected["variables"]]
                arrays = {name: context.data[name] for name in columns}
                size = len(arrays[axis])
                count = min(size, limit)
                return {
                    **selected,
                    "dtype": str(arrays[axis].dtype),
                    "columns": columns,
                    "column_kinds": {axis: "axis"}
                    | {name: "variable" for name in selected["variables"]},
                    "data": [
                        {name: json_value(arrays[name][index]) for name in columns}
                        for index in range(count)
                    ],
                    "truncated": size > count,
                }
            name = selected["variable"]
            value = context.data[name]
            axes = selected["axes"]
            if selected["kind"] == "relation":
                num_nodes = context.num_nodes or 0
                relation_limit = min(limit, len(value))
                candidate_axes = []
                for order, axis in enumerate(context.axis_names()):
                    if len(context.data[axis]) != num_nodes:
                        continue
                    uses_as_structure_axis = sum(
                        (
                            dimensions and dimensions[-1] == axis
                            for variable, dimensions in context.variable_axes.items()
                            if variable not in context.relation_names
                            and variable not in context.variable_structures
                        )
                    )
                    if uses_as_structure_axis:
                        candidate_axes.append((-uses_as_structure_axis, order, axis))
                node_axis = min(candidate_axes)[2] if candidate_axes else None
                labels = context.data[node_axis] if node_axis is not None else np.arange(num_nodes)
                max_nodes = 160
                if num_nodes <= max_nodes:
                    node_ids = list(range(num_nodes))
                else:
                    node_ids = []
                    seen = set()
                    for row in value[:relation_limit]:
                        for endpoint in row:
                            endpoint = int(endpoint)
                            if endpoint not in seen and len(node_ids) < max_nodes:
                                seen.add(endpoint)
                                node_ids.append(endpoint)
                visible_nodes = set(node_ids)
                coordinates = [
                    row
                    for row in value[:relation_limit]
                    if all((int(endpoint) in visible_nodes for endpoint in row))
                ]
                return {
                    **selected,
                    "description": context.variable_descriptions.get(name, ""),
                    "values": json_value(value[:relation_limit]),
                    "axis_values": {
                        axis: json_value(context.data[axis][:limit])
                        for axis in axes
                        if axis in context.data
                    },
                    "node_axis": node_axis,
                    "nodes": [{"id": node, "label": json_value(labels[node])} for node in node_ids],
                    "coordinates": json_value(np.asarray(coordinates)),
                    "endpoint_count": int(value.shape[1]),
                    "relation_count": int(value.shape[0]),
                    "truncated": len(coordinates) < len(value) or len(node_ids) < num_nodes,
                }
            result = {
                **selected,
                "description": context.variable_descriptions.get(name, ""),
                "axis_values": {axis: json_value(context.data[axis][:limit]) for axis in axes},
                "axis_truncated": {axis: len(context.data[axis]) > limit for axis in axes},
            }
            if value.ndim == 2:
                row_count = min(value.shape[0], limit)
                column_count = min(value.shape[1], limit)
                result.update(
                    {
                        "values": json_value(value[:row_count, :column_count]),
                        "truncated": [value.shape[0] > row_count, value.shape[1] > column_count],
                    }
                )
            elif value.ndim >= 3:
                flattened = value.reshape(-1)
                result["sample_values"] = json_value(flattened[: min(8, flattened.size)])
                if value.dtype.kind in "iufcb" and flattened.size:
                    numeric = np.asarray(flattened, dtype=float)
                    finite = numeric[np.isfinite(numeric)]
                    if finite.size:
                        result["value_range"] = [float(finite.min()), float(finite.max())]
            return result

    def data_context_plot(
        x: str, y: str, hue: str | None = None, size: str | None = None, limit: int = 2000
    ):
        limit = max(1, min(limit, 5000))
        with session.lock:
            context = available_variable_context(session.context)
            selected = {
                channel: name
                for channel, name in {"x": x, "y": y, "hue": hue, "size": size}.items()
                if name
            }
            missing = sorted(set(selected.values()) - set(context.data))
            if missing:
                raise ServiceError(404, f"Unknown context variables: {missing}")
            axis_names = set(context.axis_names())
            dimensions = {
                name: (name,) if name in axis_names else context.variable_axes[name]
                for name in selected.values()
            }
            repeated = {
                name: axes for name, axes in dimensions.items() if len(set(axes)) != len(axes)
            }
            if repeated:
                raise ServiceError(400, f"Repeated axis names are not supported: {repeated}")
            broadcast_axes = list(
                dict.fromkeys((axis for name in selected.values() for axis in dimensions[name]))
            )
            broadcast_shape = tuple((len(context.data[axis]) for axis in broadcast_axes))
            total = int(np.prod(broadcast_shape, dtype=np.int64)) if broadcast_shape else 1
            count = min(total, limit)
            flat_indices = (
                np.arange(total, dtype=np.int64)
                if total <= limit
                else np.linspace(0, total - 1, count, dtype=np.int64)
            )
            coordinates = np.unravel_index(flat_indices, broadcast_shape) if broadcast_shape else ()
            values = {}
            numeric = {}
            for name in selected.values():
                value = context.data[name]
                source_axes = dimensions[name]
                permutation = sorted(
                    range(len(source_axes)),
                    key=lambda index: broadcast_axes.index(source_axes[index]),
                )
                ordered_axes = tuple((source_axes[index] for index in permutation))
                aligned = np.transpose(value, permutation) if permutation else value
                aligned_shape = tuple(
                    (
                        aligned.shape[ordered_axes.index(axis)] if axis in ordered_axes else 1
                        for axis in broadcast_axes
                    )
                )
                broadcast = np.broadcast_to(aligned.reshape(aligned_shape), broadcast_shape)
                sampled = (
                    broadcast[coordinates] if broadcast_shape else np.asarray([broadcast.item()])
                )
                values[name] = json_value(sampled)
                numeric[name] = value.dtype.kind in "iufcb"
            return {
                "channels": selected,
                "axes": broadcast_axes,
                "shape": list(broadcast_shape),
                "total": total,
                "count": count,
                "truncated": total > count,
                "values": values,
                "numeric": numeric,
            }

    def data_context_heatmap(payload: dict = None):
        with session.lock:
            context = available_variable_context(session.context)
            raw_row = payload.get("row", [])
            raw_column = payload.get("column", [])
            if not isinstance(raw_row, list) or not isinstance(raw_column, list):
                raise ServiceError(400, "row and column must be lists")
            row = [str(name) for name in raw_row]
            column = [str(name) for name in raw_column]
            color = str(payload.get("color", ""))
            z = str(payload.get("z", ""))
            try:
                z_index = int(payload.get("z_index", 0))
            except (TypeError, ValueError) as exc:
                raise ServiceError(400, "z_index must be an integer") from exc
            axis_names = set(context.axis_names())
            names = {*row, *column, *([color] if color else []), *([z] if z else [])}
            missing = sorted(names - set(context.data))
            if missing:
                raise ServiceError(404, f"Unknown context variables: {missing}")
            if color:
                if color in axis_names:
                    raise ServiceError(400, "Color must be a two- or three-dimensional variable")
                color_axes = context.variable_axes[color]
                if len(color_axes) not in {2, 3}:
                    raise ServiceError(400, "Color must be a two- or three-dimensional variable")
                if len(row) != 1 or row[0] not in axis_names:
                    raise ServiceError(400, "Row must contain exactly one axis")
                if len(column) != 1 or column[0] not in axis_names:
                    raise ServiceError(400, "Column must contain exactly one axis")
                row_axis, column_axis = (row[0], column[0])
                if (
                    row_axis == column_axis
                    or row_axis not in color_axes
                    or column_axis not in color_axes
                ):
                    raise ServiceError(
                        400, "Row and column must be different axes of the color variable"
                    )
                remaining = [axis for axis in color_axes if axis not in {row_axis, column_axis}]
                if remaining:
                    if z != remaining[0]:
                        raise ServiceError(
                            400, f"Z must be the remaining color axis {remaining[0]!r}"
                        )
                    z_size = len(context.data[z])
                    if not 0 <= z_index < z_size:
                        raise ServiceError(400, f"z_index must be in [0, {z_size})")
                    matrix = np.take(context.data[color], z_index, axis=color_axes.index(z))
                    remaining_axes = tuple((axis for axis in color_axes if axis != z))
                    z_value = json_value(context.data[z][z_index])
                else:
                    if z:
                        raise ServiceError(
                            400, "Z is only used with a three-dimensional color variable"
                        )
                    matrix = context.data[color]
                    remaining_axes = color_axes
                    z_size = 0
                    z_value = None
                if remaining_axes != (row_axis, column_axis):
                    matrix = np.transpose(
                        matrix, (remaining_axes.index(row_axis), remaining_axes.index(column_axis))
                    )
                row_labels = context.data[row_axis]
                column_labels = context.data[column_axis]
                mode = "tensor"
            else:
                row_is_axis = len(row) == 1 and row[0] in axis_names
                column_is_axis = len(column) == 1 and column[0] in axis_names
                if row_is_axis == column_is_axis:
                    raise ServiceError(
                        400,
                        (
                            "Place one axis in row or colum"
                            "n and aligned one-dimensional "
                            "variables on the other side"
                        ),
                    )
                axis = row[0] if row_is_axis else column[0]
                variables = column if row_is_axis else row
                if not variables:
                    raise ServiceError(400, "Select at least one aligned one-dimensional variable")
                invalid = [
                    name
                    for name in variables
                    if name in axis_names or context.variable_axes[name] != (axis,)
                ]
                if invalid:
                    raise ServiceError(400, f"Variables must use only axis {axis!r}: {invalid}")
                arrays = [context.data[name] for name in variables]
                if row_is_axis:
                    matrix = np.column_stack(arrays)
                    row_axis, column_axis = (axis, "variables")
                    row_labels, column_labels = (context.data[axis], np.asarray(variables))
                else:
                    matrix = np.vstack(arrays)
                    row_axis, column_axis = ("variables", axis)
                    row_labels, column_labels = (np.asarray(variables), context.data[axis])
                z_size = 0
                z_value = None
                mode = "aligned_variables"
            row_count = min(matrix.shape[0], 80)
            column_count = min(matrix.shape[1], 80)
            shown = matrix[:row_count, :column_count]
            return {
                "mode": mode,
                "row_axis": row_axis,
                "column_axis": column_axis,
                "row_labels": json_value(row_labels[:row_count]),
                "column_labels": json_value(column_labels[:column_count]),
                "values": json_value(shown),
                "shape": list(matrix.shape),
                "dtype": str(matrix.dtype),
                "numeric": matrix.dtype.kind in "iufcb",
                "truncated": row_count < matrix.shape[0] or column_count < matrix.shape[1],
                "z_axis": z or None,
                "z_index": z_index if z else None,
                "z_value": z_value,
                "z_size": z_size,
            }

    def reload_data_context():
        try:
            return session.reload_context_data()
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc

    def update_data_selection(payload: dict = None):
        with session.lock:
            if session.data_state in {"running", "stopping"}:
                raise ServiceError(
                    409,
                    "Wait for the data-preparation agent to finish before changing variable roles",
                )
            if session.state not in {"idle", "running"}:
                raise ServiceError(409, "Variable roles cannot be changed in the current run state")
            if session.state == "running":
                control_status = session.sr_interaction_manager.status()
                if not control_status["interaction_state"] == "paused":
                    raise ServiceError(
                        409,
                        (
                            "Pause symbolic regression and "
                            "wait for the safe-boundary ack"
                            "nowledgement before changing v"
                            "ariable roles"
                        ),
                    )
            target = str(payload.get("target", "")).strip()
            features = payload.get("features")
            if not isinstance(features, list) or any(
                (not isinstance(name, str) for name in features)
            ):
                raise ServiceError(400, "features must be a list of variable names")
            try:
                descriptions = payload.get("variable_descriptions", {})
                if not isinstance(descriptions, dict) or any(
                    (
                        not isinstance(name, str) or not isinstance(value, str)
                        for name, value in descriptions.items()
                    )
                ):
                    raise ValueError("variable_descriptions must map variable names to text")
                descriptions = {name: value.strip() for name, value in descriptions.items()}
                manifest_path = session.workspace / "context.data" / "manifest.json"
                if manifest_path.is_file():
                    update_context_data_descriptions(
                        manifest_path.parent, descriptions, workspace=session.workspace_manager
                    )
                change = session.select_variables(
                    target=target, features=features, variable_descriptions=descriptions
                )
            except (OSError, ValueError) as exc:
                raise ServiceError(400, str(exc)) from exc
            session.variable_descriptions = dict(session.context.variable_descriptions)
            return {**change, "context": session.context.schema()}

    def update_data_descriptions(payload: dict = None):
        with session.lock:
            if session.data_state in {"running", "stopping"}:
                raise ServiceError(
                    409,
                    (
                        "Wait for the data-preparation "
                        "agent to finish before changin"
                        "g variable descriptions"
                    ),
                )
            if session.state == "running":
                control_status = session.sr_interaction_manager.status()
                if not control_status["interaction_state"] == "paused":
                    raise ServiceError(
                        409,
                        (
                            "Pause symbolic regression and "
                            "wait for the safe-boundary ack"
                            "nowledgement before changing v"
                            "ariable descriptions"
                        ),
                    )
            descriptions = payload.get("variable_descriptions", {})
            if not isinstance(descriptions, dict) or any(
                (
                    not isinstance(name, str) or not isinstance(value, str)
                    for name, value in descriptions.items()
                )
            ):
                raise ServiceError(400, "variable_descriptions must map variable names to text")
            descriptions = {name: value.strip() for name, value in descriptions.items()}
            manifest_path = session.workspace / "context.data" / "manifest.json"
            try:
                if manifest_path.is_file():
                    update_context_data_descriptions(
                        manifest_path.parent, descriptions, workspace=session.workspace_manager
                    )
                elif unknown := (set(descriptions) - set(session.context.data)):
                    raise ValueError(f"unknown context variables: {sorted(unknown)}")
            except (OSError, ValueError) as exc:
                raise ServiceError(400, str(exc)) from exc
            changed = False
            for name in session.context.data:
                if (
                    name in descriptions
                    and session.context.variable_descriptions[name] != descriptions[name]
                ):
                    session.context.variable_descriptions[name] = descriptions[name]
                    changed = True
            if changed:
                session.context.args.data_revision += 1
            session.variable_descriptions = dict(session.context.variable_descriptions)
            return session.context.schema()

    def settings(payload: dict = None):
        try:
            return session.configure(payload)
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc

    def resolve(path, *, access="read"):
        try:
            return session.resolve(path, access=access)
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc

    def files(path: str = "", recursive: bool = False):
        with session.lock:
            directory = resolve(path)
            if not directory.is_dir():
                raise ServiceError(404, "Directory not found")
            readonly_roots = {logical.name for logical in session.workspace_manager.mount_map}

            def list_entries(logical_directory, resolved_directory, ancestors=frozenset()):
                try:
                    identity = (resolved_directory.stat().st_dev, resolved_directory.stat().st_ino)
                except FileNotFoundError:
                    return []
                if identity in ancestors:
                    return []
                descendants = ancestors | {identity}
                entries = []
                for item in resolved_directory.iterdir():
                    logical = logical_directory / item.name
                    try:
                        resolved = resolve(str(logical))
                        is_directory = resolved.is_dir()
                        mounted = bool(logical.parts and logical.parts[0] in readonly_roots)
                        locked = not mounted and session.workspace_manager.is_locked(logical)
                        entry = {
                            "name": item.name,
                            "path": str(logical),
                            "directory": is_directory,
                            "read_only": mounted or locked,
                            "mounted": mounted,
                            "locked": locked,
                        }
                        if is_directory:
                            children = list_entries(logical, resolved, descendants)
                            entry["size"] = None
                            if recursive:
                                entry["children"] = children
                        else:
                            with session.workspace_manager.safe_open(resolved, "rb") as stream:
                                entry["size"] = os.fstat(stream.fileno()).st_size
                        entries.append(entry)
                    except (FileNotFoundError, ServiceError):
                        continue
                return sorted(
                    entries,
                    key=lambda entry: (
                        not entry["directory"],
                        entry["name"].lower(),
                        entry["name"],
                    ),
                )

            entries = list_entries(Path(path), directory)
            return {"path": path, "entries": entries}

    def workspace_item_size(path: str):
        with session.lock:
            item = resolve(path)
            if item.is_file():
                with session.workspace_manager.safe_open(item, "rb") as stream:
                    return {"path": path, "size": os.fstat(stream.fileno()).st_size}
            if not item.is_dir():
                raise ServiceError(404, "File or directory not found")
            total = 0
            for current, _, filenames in os.walk(item):
                relative_directory = Path(current).relative_to(item)
                for filename in filenames:
                    relative = relative_directory / filename
                    try:
                        source = resolve(str(Path(path) / relative))
                    except ServiceError:
                        continue
                    if source.is_file():
                        with session.workspace_manager.safe_open(source, "rb") as stream:
                            total += os.fstat(stream.fileno()).st_size
            return {"path": path, "size": total}

    def download(path: str):
        with session.lock:
            item = resolve(path)
            if item.is_file():
                stream = session.workspace_manager.safe_open(item, "rb")
                return stream_download(
                    iter(lambda: stream.read(1024 * 1024), b""),
                    media_type="application/octet-stream",
                    headers={
                        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(item.name)
                    },
                    background=cleanup_callback(stream.close),
                )
            if not item.is_dir():
                raise ServiceError(404, "File or directory not found")
            descriptor, archive_name = tempfile.mkstemp(suffix=".zip")
            os.close(descriptor)
            archive = Path(archive_name)
            try:
                with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as output:
                    for current, directories, filenames in os.walk(item):
                        current_path = Path(current)
                        relative_directory = current_path.relative_to(item)
                        if not directories and (not filenames):
                            output.writestr(str(Path(item.name) / relative_directory) + "/", "")
                        for filename in filenames:
                            relative = relative_directory / filename
                            try:
                                source = resolve(str(Path(path) / relative))
                            except ServiceError:
                                continue
                            if source.is_file():
                                archive_path = (Path(item.name) / relative).as_posix()
                                with session.workspace_manager.safe_open(
                                    source, "rb"
                                ) as input_stream:
                                    with output.open(archive_path, "w") as output_stream:
                                        shutil.copyfileobj(input_stream, output_stream)
            except Exception:
                archive.unlink(missing_ok=True)
                raise
            return file_download(
                archive,
                filename=f"{item.name}.zip",
                media_type="application/zip",
                background=cleanup_callback(archive.unlink, missing_ok=True),
            )

    def preview(path: str):
        with session.lock:
            file = resolve(path)
            if not file.is_file():
                raise ServiceError(404, "File not found")
            if file.suffix.lower() == ".npy":
                try:
                    with session.workspace_manager.safe_open(file, "rb") as stream:
                        array = np.load(stream, allow_pickle=False)
                    text = np.array2string(array, threshold=1000, edgeitems=4, max_line_width=120)
                except (OSError, TypeError, ValueError) as exc:
                    raise ServiceError(400, f"Unable to preview NPY file safely: {exc}") from exc
                truncated = array.size > 1000 or len(text) > 65536
                return {
                    "kind": "npy",
                    "shape": list(array.shape),
                    "dtype": str(array.dtype),
                    "size": int(array.size),
                    "text": text[:65536],
                    "truncated": truncated,
                }
            with session.workspace_manager.safe_open(file, "rb") as stream:
                data = stream.read(65537)
            return {
                "kind": "text",
                "text": data[:65536].decode("utf-8", errors="replace"),
                "truncated": len(data) > 65536,
            }

    def create_directory(payload: dict = None):
        path = str(payload.get("path", "")).strip()
        if not path:
            raise ServiceError(400, "Directory path is required")
        with session.lock:
            try:
                session.workspace_manager.create_directory(path)
            except FileExistsError as exc:
                raise ServiceError(409, "A file or directory already exists at this path") from exc
            except ServiceError:
                raise
            except (OSError, ValueError) as exc:
                raise ServiceError(400, str(exc)) from exc
        return {"path": path}

    def set_workspace_item_lock(payload: dict = None):
        path = str(payload.get("path", "")).strip()
        locked = payload.get("locked")
        if not path:
            raise ServiceError(400, "The workspace root cannot be locked")
        if not isinstance(locked, bool):
            raise ServiceError(400, "locked must be a boolean")
        with session.lock:
            try:
                session.workspace_manager.set_locked(path, locked)
            except (OSError, ValueError) as exc:
                raise ServiceError(400, str(exc)) from exc
        return {"path": path, "locked": locked}

    def move_workspace_item(payload: dict = None):
        source_path = str(payload.get("source", "")).strip()
        destination_path = str(payload.get("destination", "")).strip()
        if not source_path or not destination_path:
            raise ServiceError(400, "Source and destination paths are required")
        with session.lock:
            try:
                session.workspace_manager.move(source_path, destination_path)
            except FileNotFoundError as exc:
                raise ServiceError(404, "Source file or directory not found") from exc
            except FileExistsError as exc:
                raise ServiceError(
                    409, "A file or directory already exists at the destination"
                ) from exc
            except ServiceError:
                raise
            except (OSError, ValueError) as exc:
                raise ServiceError(400, str(exc)) from exc
        return {"source": source_path, "destination": destination_path}

    def delete_workspace_item(path: str):
        path = path.strip()
        if not path:
            raise ServiceError(400, "The workspace root cannot be deleted")
        with session.lock:
            try:
                session.workspace_manager.remove(path, recursive=True)
            except FileNotFoundError as exc:
                raise ServiceError(404, "File or directory not found") from exc
            except ServiceError:
                raise
            except (OSError, ValueError) as exc:
                raise ServiceError(400, str(exc)) from exc
        return {"path": path}

    def csv_files():
        with session.lock:
            files = [
                str(relative)
                for relative, path in session.workspace_manager.iter_files()
                if path.suffix.lower() in {".csv", ".xlsx"}
            ]
            return {"files": sorted(files)}

    def data_preview(path: str, rows: int = 300):
        rows = max(5, min(rows, 1000))
        with session.lock:
            file = resolve(path)
            if file.suffix.lower() not in {".csv", ".xlsx"} or not file.is_file():
                raise ServiceError(400, "Select an existing CSV or Excel file")
            try:
                with session.workspace_manager.safe_open(file, "rb") as stream:
                    frame = (
                        pd.read_excel(stream, nrows=rows + 1)
                        if file.suffix.lower() == ".xlsx"
                        else pd.read_csv(stream, nrows=rows + 1)
                    )
            except Exception as exc:
                raise ServiceError(400, f"Unable to read table: {exc}") from exc
        if frame.empty or len(frame.columns) < 2:
            raise ServiceError(400, "CSV needs at least two columns and one row")
        columns = [str(column) for column in frame.columns]
        if len(set(columns)) != len(columns):
            raise ServiceError(400, "CSV column names must be unique")
        frame.columns = columns
        truncated = len(frame) > rows
        frame = frame.iloc[:rows]
        numeric = {column: bool(pd.api.types.is_numeric_dtype(frame[column])) for column in columns}
        serializable = frame.astype(object).where(frame.notna(), None)
        serializable = serializable.replace([float("inf"), float("-inf")], None)
        records = serializable.to_dict(orient="records")
        return {
            "path": path,
            "columns": columns,
            "numeric": numeric,
            "rows": records,
            "truncated": truncated,
        }

    def discovery_tasks():
        from .discovery import list_cases

        return {"tasks": list_cases()}

    def load_discovery_task(payload: dict = None):
        from .discovery import load_case

        try:
            return load_case(session, str(payload.get("name", "")))
        except FileNotFoundError as exc:
            raise ServiceError(404, str(exc)) from exc
        except FileExistsError as exc:
            raise ServiceError(409, str(exc)) from exc
        except (ValueError, OSError) as exc:
            raise ServiceError(400, str(exc)) from exc

    def create_demo(payload: dict | None = None):
        try:
            path = session.create_demo(str((payload or {}).get("kind", "polynomial")))
        except FileExistsError as exc:
            raise ServiceError(409, str(exc)) from exc
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc
        relative = str(path.relative_to(session.workspace))
        size = sum((file.stat().st_size for file in path.iterdir() if file.is_file()))
        session.data_interaction_manager.publish_event(
            "workspace_changed", {"operation": "created", "path": relative, "size": size}
        )
        return {"path": relative}

    def initial_prompts(payload: dict = None):
        try:
            return session.preview_initial_prompts(payload)
        except (ValueError, OSError, pd.errors.ParserError) as exc:
            raise ServiceError(400, str(exc)) from exc

    return {
        "status": status,
        "capabilities": capabilities,
        "start": start,
        "prepare_data": prepare_data,
        "data_agent_events": data_agent_events,
        "stop_data_preparation": stop_data_preparation,
        "configure_data_agent": configure_data_agent,
        "test_data_agent_model": test_data_agent_model,
        "test_model": test_model,
        "evaluator_configuration": evaluator_configuration,
        "configure_evaluator": configure_evaluator,
        "test_evaluator": test_evaluator,
        "start_evaluator_assistance": start_evaluator_assistance,
        "evaluator_agent_events": evaluator_agent_events,
        "stop_evaluator_assistance": stop_evaluator_assistance,
        "configure_evaluator_agent": configure_evaluator_agent,
        "test_evaluator_agent_model": test_evaluator_agent_model,
        "data_context": data_context,
        "data_context_preview": data_context_preview,
        "data_context_plot": data_context_plot,
        "data_context_heatmap": data_context_heatmap,
        "reload_data_context": reload_data_context,
        "update_data_selection": update_data_selection,
        "update_data_descriptions": update_data_descriptions,
        "settings": settings,
        "files": files,
        "workspace_item_size": workspace_item_size,
        "download": download,
        "preview": preview,
        "create_directory": create_directory,
        "set_workspace_item_lock": set_workspace_item_lock,
        "move_workspace_item": move_workspace_item,
        "delete_workspace_item": delete_workspace_item,
        "csv_files": csv_files,
        "data_preview": data_preview,
        "discovery_tasks": discovery_tasks,
        "load_discovery_task": load_discovery_task,
        "create_demo": create_demo,
        "initial_prompts": initial_prompts,
    }
