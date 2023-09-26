# openai_manager

OpenAI Manager is a server app for keeping track of API calls. It solves a set of problems:
1. You can give access to making API calls without giving anyone your Secret Key
2. You can book keep all API calls made on specific projects for specific users.
3. You can restrict how much money projects or individual users on a project can spend.

OpenAI manager does this by acting as a proxy for API endpoints and providing a set of data objects that let you create Projects, Users, External API Keys and Internal API Keys that all keep track of who is making api calls for which project on which models and ultimately calculating costs per user, and per project. 

The index page gives a good overview of how it is structured.

![image](https://github.com/arthurhjorth/openai_manager/assets/1860843/4f6d7b7e-53ee-4dfa-acc2-2898ffcb4929)

**Projects**
When you define a project, you decide: 
1. Which API key will it use (this is an actual secret key).
2. What is the spending limit on a project in USD.
3. Which users are allowed to make API calls on behalf of the project.
4. Project lead users (they can add, remove users on a project)
5. Which models are allowed on this project.

When you have defined and saved a project, you get this:

<img width="300" alt="image" src="https://github.com/arthurhjorth/openai_manager/assets/1860843/f9f8edf9-6c58-404a-8d62-94d3a6dfc623">

This tells you the name of the project, which External API key is used for the project, and then lists all users for the project including their _Internal_ API key. 

**External API Keys**
You can also add new External API keys. These are your secret keys.

<img width="317" alt="image" src="https://github.com/arthurhjorth/openai_manager/assets/1860843/2697b494-7436-497a-b141-eaedc77a3931">

When you add a new External API key, the server makes a request to the Embeddings API with the phrase "test" to see if the API key works. If it does, it is added to the server.

**Models**
You can add model names to the server. 
<img width="639" alt="image" src="https://github.com/arthurhjorth/openai_manager/assets/1860843/2fdc487d-3475-4d8e-b3d0-45390f84047e">

All models are associated with a Cost, and a Cost has a start date and end date. This ensure correct book keeping for projects that span changes to the API costs. if the price of a model changes, you can just add a new cost object with the corresponding date. The old cost object will end on the day before.

<img width="592" alt="image" src="https://github.com/arthurhjorth/openai_manager/assets/1860843/f80c883f-df1e-491b-9abc-f2a87c8d2283">

**Users**
This should be self explanatory, but you can add Users. They go on projects.
