# Port 30000 deployment

The previous Python WebUI deployment has been replaced by the root Compose stack.
Set WEB_PORT=30000 and follow [the decoupled deployment guide](../decoupled/README.md).
The old OpenRouter credential-injecting gateway is no longer used: model configurations
and encrypted credentials are managed by Next.js, and personal keys are never overwritten.
