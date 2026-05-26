---
trigger: always_on
---
- Do not create new functions if existing functions can be generalized and reused
- Always use the configuration files for all parameters
- Do not assign values directly in the code, use configuration files instead
- Use constants for all magic numbers and string literals and read it from a file like a configuration
- Always check the impact of changes in the api routes and models on the frontend
- Use model files instead of hardcoded strings for the responses and request objects
- Use info logs only on initialization where the log is once per application start
- Use debug or trace logs only if required for debugging purposes and remove them before committing
- Keep the code for functional logic in separate modules
- Use static functions only for the utility functions
- Use classes only for the stateful objects and avoid global state

