// Generated from contracts/harness.openapi.json.
export const scientificRoutes = [
  {
    "method": "GET",
    "path": "/"
  },
  {
    "method": "POST",
    "path": "/control/command"
  },
  {
    "method": "GET",
    "path": "/control/status"
  },
  {
    "method": "GET",
    "path": "/operations/{operation_id}"
  },
  {
    "method": "GET",
    "path": "/control/events"
  },
  {
    "method": "GET",
    "path": "/control/events/{sequence}"
  },
  {
    "method": "GET",
    "path": "/data/agent/events/{sequence}"
  },
  {
    "method": "GET",
    "path": "/evaluator/agent/events/{sequence}"
  },
  {
    "method": "GET",
    "path": "/records"
  },
  {
    "method": "GET",
    "path": "/candidates"
  },
  {
    "method": "GET",
    "path": "/records/{node_id}"
  },
  {
    "method": "GET",
    "path": "/export"
  },
  {
    "method": "PUT",
    "path": "/workspace/upload"
  },
  {
    "method": "GET",
    "path": "/capabilities"
  },
  {
    "method": "POST",
    "path": "/start"
  },
  {
    "method": "POST",
    "path": "/data/agent"
  },
  {
    "method": "GET",
    "path": "/data/agent/events"
  },
  {
    "method": "POST",
    "path": "/data/agent/stop"
  },
  {
    "method": "PUT",
    "path": "/data/agent/settings"
  },
  {
    "method": "POST",
    "path": "/data/agent/test"
  },
  {
    "method": "POST",
    "path": "/test"
  },
  {
    "method": "GET",
    "path": "/evaluator"
  },
  {
    "method": "PUT",
    "path": "/evaluator"
  },
  {
    "method": "POST",
    "path": "/evaluator/test"
  },
  {
    "method": "POST",
    "path": "/evaluator/agent/start"
  },
  {
    "method": "GET",
    "path": "/evaluator/agent/events"
  },
  {
    "method": "POST",
    "path": "/evaluator/agent/stop"
  },
  {
    "method": "PUT",
    "path": "/evaluator/agent/settings"
  },
  {
    "method": "POST",
    "path": "/evaluator/agent/test"
  },
  {
    "method": "GET",
    "path": "/data/context"
  },
  {
    "method": "GET",
    "path": "/data/context/preview"
  },
  {
    "method": "GET",
    "path": "/data/context/plot"
  },
  {
    "method": "POST",
    "path": "/data/context/heatmap"
  },
  {
    "method": "POST",
    "path": "/data/context/reload"
  },
  {
    "method": "PUT",
    "path": "/data/selection"
  },
  {
    "method": "PUT",
    "path": "/data/descriptions"
  },
  {
    "method": "POST",
    "path": "/settings"
  },
  {
    "method": "GET",
    "path": "/workspace"
  },
  {
    "method": "PATCH",
    "path": "/workspace"
  },
  {
    "method": "DELETE",
    "path": "/workspace"
  },
  {
    "method": "GET",
    "path": "/workspace/size"
  },
  {
    "method": "GET",
    "path": "/workspace/download"
  },
  {
    "method": "GET",
    "path": "/workspace/preview"
  },
  {
    "method": "POST",
    "path": "/workspace/directory"
  },
  {
    "method": "PUT",
    "path": "/workspace/lock"
  },
  {
    "method": "GET",
    "path": "/data/csv-files"
  },
  {
    "method": "GET",
    "path": "/data/preview"
  },
  {
    "method": "GET",
    "path": "/data/discovery-tasks"
  },
  {
    "method": "POST",
    "path": "/data/discovery-tasks/load"
  },
  {
    "method": "POST",
    "path": "/data/demo"
  },
  {
    "method": "POST",
    "path": "/data/prompts"
  }
] as const;
