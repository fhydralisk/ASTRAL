"""Audit the scientific handoff without fitting or selecting a formula."""
from ..core import load_context_data
from ..evaluator.observational_contract import audit_contract, read_contract
from .base_tool import BaseTool, ToolMetadata


@BaseTool.register("validate_discovery_contract")
class ValidateDiscoveryContractTool(BaseTool):
    metadata = ToolMetadata(name="validate_discovery_contract")

    def execute(self) -> dict:
        """Validate discovery_contract.json roles, aligned arrays and declared group split.

        Reads the full context.data on disk so auxiliary metadata need not become
        predictors. This validates the declared split, not the active evaluator.
        See prepare-discovery-handoff skill for the schema and stage responsibilities.
        """
        workspace = self.context.workspace
        contract = read_contract(workspace)
        if contract is None:
            return {"valid": False, "errors": ["Create discovery_contract.json using prepare-discovery-handoff skill"]}
        loaded = load_context_data(workspace.path / "context.data", workspace=workspace)
        return audit_contract(contract, loaded["data"])
