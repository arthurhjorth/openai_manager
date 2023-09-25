# openai_manager

OpenAI Manager is a server app for keeping track of API calls. It solves two problems:
1. You can give access to making API calls without giving anyone your Secret Key
2. You can book keep all projects and users individually.

OpenAI manager does this by acting as a proxy for API endpoints and providing a set of data objects that let you create Projects, Users, and Internal API keys that all keep track of who is making api calls for which project on which models and ultimately calculating costs per user, and per project. 

