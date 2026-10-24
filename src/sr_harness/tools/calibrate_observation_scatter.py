"""Calibrate a declared regression observation model before formula search."""
import json

from ..core import load_context_data
from ..evaluator.observational_contract import read_contract
from ..evaluator.noise_calibration import estimate_affine_scatter
from .base_tool import BaseTool, ToolMetadata


@BaseTool.register('calibrate_observation_scatter')
class CalibrateObservationScatterTool(BaseTool):
    metadata = ToolMetadata(name='calibrate_observation_scatter')

    def execute(self, apply: bool = False) -> dict:
        """Estimate an extra residual scale from a fixed affine training baseline.

        Use only when formal independent symmetric errors omit residual scatter,
        as allowed by the task's observation model. Fits only declared training
        rows using all allowed predictors and never validation responses. The
        scale includes baseline misspecification, not just physical scatter.
        Freeze this before formula search; changing it requires a new search.

        Args:
            apply: Save extra_scatter and calibration provenance into the
                discovery contract. False previews without changing any file.
        """
        workspace = self.context.workspace
        if workspace is None:
            raise ValueError('A workspace with context.data and discovery_contract.json is required')
        contract = read_contract(workspace)
        if contract is None:
            raise ValueError('Create and validate discovery_contract.json before calibration')
        data = load_context_data(workspace.path / 'context.data', workspace=workspace)['data']
        result = estimate_affine_scatter(data, contract)
        if apply:
            if read_contract(workspace) != contract:
                raise ValueError('Discovery contract changed during calibration; retry from the current contract')
            updated = dict(contract)
            updated['extra_scatter'] = result['extra_scatter']
            updated['extra_scatter_calibration'] = result
            with workspace.open_for_write('discovery_contract.json', 'w', encoding='utf-8') as stream:
                json.dump(updated, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write('\n')
        return {**result, 'applied': bool(apply)}
