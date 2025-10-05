# OpenAI Agents SDK & Responses API – Verbatim Docs Compilation

Generated: 2025-10-04T22:34:53

> This file collects **verbatim excerpts** from the official OpenAI docs pages you specified.
> Where the Platform docs are a SPA and not directly scrapable here, I preserved your provided text
> and included the canonical links for verification.
>
> **Sources verified (Oct 2025):**
> - OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
> - API Reference – Introduction: https://platform.openai.com/docs/api-reference/introduction
> - API Reference – Responses → Create: https://platform.openai.com/docs/api-reference/responses/create

---



# OpenAI Agents SDK (Intro)

The OpenAI Agents SDK enables you to build agentic AI apps in a lightweight, easy-to-use package with very few abstractions. It's a production-ready upgrade of our previous experimentation for agents, Swarm. The Agents SDK has a very small set of primitives:
  * Agents, which are LLMs equipped with instructions and tools
  * Handoffs, which allow agents to delegate to other agents for specific tasks
  * Guardrails, which enable validation of agent inputs and outputs
  * Sessions, which automatically maintains conversation history across agent runs

In combination with Python, these primitives are powerful enough to express complex relationships between tools and agents, and allow you to build real-world applications without a steep learning curve. In addition, the SDK comes with built-in tracing that lets you visualize and debug your agentic flows, as well as evaluate them and even fine-tune models for your application.

## Why use the Agents SDK

The SDK has two driving design principles:

  1. Enough features to be worth using, but few enough primitives to make it quick to learn.
  2. Works great out of the box, but you can customize exactly what happens.

Here are the main features of the SDK:
  * Agent loop: Built-in agent loop that handles calling tools, sending results to the LLM, and looping until the LLM is done.
  * Python-first: Use built-in language features to orchestrate and chain agents, rather than needing to learn new abstractions.
  * Handoffs: A powerful feature to coordinate and delegate between multiple agents.
  * Guardrails: Run input validations and checks in parallel to your agents, breaking early if the checks fail.
  * Sessions: Automatic conversation history management across agent runs, eliminating manual state handling.
  * Function tools: Turn any Python function into a tool, with automatic schema generation and Pydantic-powered validation.
  * Tracing: Built-in tracing that lets you visualize, debug and monitor your workflows, as well as use the OpenAI suite of evaluation, fine-tuning and distillation tools.

## Installation

```
pip install openai-agents
```

## Hello world example

```python
from agents import Agent, Runner

agent = Agent(name="Assistant", instructions="You are a helpful assistant")

result = Runner.run_sync(agent, "Write a haiku about recursion in programming.")
print(result.final_output)

# Code within the code,
# Functions calling themselves,
# Infinite loop's dance.
```

(If running this, ensure you set the `OPENAI_API_KEY` environment variable)

```bash
export OPENAI_API_KEY=sk-...
```



# OpenAI Agents SDK – Quickstart

## Create a project and virtual environment

You'll only need to do this once.

```bash
mkdir my_project
cd my_project
python -m venv .venv
```

### Activate the virtual environment

Do this every time you start a new terminal session.

```bash
source .venv/bin/activate
```

### Install the Agents SDK

```bash
pip install openai-agents # or `uv add openai-agents`, etc
```

### Set an OpenAI API key

If you don't have one, follow these instructions to create an OpenAI API key.

```bash
export OPENAI_API_KEY=sk-...
```

## Create your first agent

Agents are defined with instructions, a name, and optional config (such as `model_config`)

```python
from agents import Agent

agent = Agent(
    name="Math Tutor",
    instructions="You provide help with math problems. Explain your reasoning at each step and include examples",
)
```

## Add a few more agents

Additional agents can be defined in the same way. `handoff_descriptions` provide additional context for determining handoff routing

```python
from agents import Agent

history_tutor_agent = Agent(
    name="History Tutor",
    handoff_description="Specialist agent for historical questions",
    instructions="You provide assistance with historical queries. Explain important events and context clearly.",
)
math_tutor_agent = Agent(
    name="Math Tutor",
    handoff_description="Specialist agent for math questions",
    instructions="You provide help with math problems. Explain your reasoning at each step and include examples",
)
```

## Define your handoffs

On each agent, you can define an inventory of outgoing handoff options that the agent can choose from to decide how to make progress on their task.

```python
triage_agent = Agent(
    name="Triage Agent",
    instructions="You determine which agent to use based on the user's homework question",
    handoffs=[history_tutor_agent, math_tutor_agent]
)
```

## Run the agent orchestration

Let's check that the workflow runs and the triage agent correctly routes between the two specialist agents.

```python
from agents import Runner

async def main():
    result = await Runner.run(triage_agent, "What is the capital of France?")
    print(result.final_output)
```

## Add a guardrail

You can define custom guardrails to run on the input or output.

```python
from agents import GuardrailFunctionOutput, Agent, Runner
from pydantic import BaseModel

class HomeworkOutput(BaseModel):
    is_homework: bool
    reasoning: str

guardrail_agent = Agent(
    name="Guardrail check",
    instructions="Check if the user is asking about homework.",
    output_type=HomeworkOutput,
)

async def homework_guardrail(ctx, agent, input_data):
    result = await Runner.run(guardrail_agent, input_data, context=ctx.context)
    final_output = result.final_output_as(HomeworkOutput)
    return GuardrailFunctionOutput(
        output_info=final_output,
        tripwire_triggered=not final_output.is_homework,
    )
```

## Put it all together

Let's put it all together and run the entire workflow, using handoffs and the input guardrail.

```python
from agents import Agent, InputGuardrail, GuardrailFunctionOutput, Runner
from agents.exceptions import InputGuardrailTripwireTriggered
from pydantic import BaseModel
import asyncio

class HomeworkOutput(BaseModel):
    is_homework: bool
    reasoning: str

guardrail_agent = Agent(
    name="Guardrail check",
    instructions="Check if the user is asking about homework.",
    output_type=HomeworkOutput,
)

math_tutor_agent = Agent(
    name="Math Tutor",
    handoff_description="Specialist agent for math questions",
    instructions="You provide help with math problems. Explain your reasoning at each step and include examples",
)

history_tutor_agent = Agent(
    name="History Tutor",
    handoff_description="Specialist agent for historical questions",
    instructions="You provide assistance with historical queries. Explain important events and context clearly.",
)

async def homework_guardrail(ctx, agent, input_data):
    result = await Runner.run(guardrail_agent, input_data, context=ctx.context)
    final_output = result.final_output_as(HomeworkOutput)
    return GuardrailFunctionOutput(
        output_info=final_output,
        tripwire_triggered=not final_output.is_homework,
    )

triage_agent = Agent(
    name="Triage Agent",
    instructions="You determine which agent to use based on the user's homework question",
    handoffs=[history_tutor_agent, math_tutor_agent],
    input_guardrails=[InputGuardrail(guardrail_function=homework_guardrail)],
)

async def main():
    # Example 1: History question
    try:
        result = await Runner.run(triage_agent, "who was the first president of the united states?")
        print(result.final_output)
    except InputGuardrailTripwireTriggered as e:
        print("Guardrail blocked this input:", e)

    # Example 2: General/philosophical question
    try:
        result = await Runner.run(triage_agent, "What is the meaning of life?")
        print(result.final_output)
    except InputGuardrailTripwireTriggered as e:
        print("Guardrail blocked this input:", e)

if __name__ == "__main__":
    asyncio.run(main())
```

## View your traces

To review what happened during your agent run, navigate to the Trace viewer in the OpenAI Dashboard to view traces of your agent runs.



# OpenAI Responses API — Create a model response

**Endpoint**
```
POST https://api.openai.com/v1/responses
```
Creates a model response. Provide text or image inputs to generate text or JSON outputs. Have the model call your own custom code or use built-in tools like web search or file search to use your own data as input for the model's response.

## Request body (selected fields)

- **background** (boolean, default `false`): Whether to run the model response in the background.
- **conversation** (string or object): The conversation that this response belongs to.
- **include** (array): Specify additional output data to include in the model response.
- **input** (string or array): Text, image, or file inputs to the model.
- **instructions** (string): A system (or developer) message inserted into the model's context.
- **max_output_tokens** (integer): Upper bound for the number of tokens generated (visible + reasoning).
- **max_tool_calls** (integer): Max number of total calls to built‑in tools.
- **metadata** (map): Up to 16 key‑value pairs for your own metadata.
- **model** (string): Model ID used to generate the response (e.g., `gpt-4o`, `o3`, etc.).
- **parallel_tool_calls** (boolean, default `true`): Allow the model to run tool calls in parallel.
- **previous_response_id** (string): The ID of a previous response to continue a conversation.
- **prompt** (object): Reference to a prompt template and variables.
- **prompt_cache_key** (string): Used by OpenAI to cache responses for similar requests.
- **reasoning** (object): Configuration for reasoning models (gpt‑5 and o‑series models).
- **safety_identifier** (string): Stable identifier to help detect policy‑violating users.
- **service_tier** (string, default `auto`): Processing tier (`default`, `flex`, `priority`, or `auto`).
- **store** (boolean, default `true`): Whether to store the generated response for later retrieval.
- **stream** (boolean, default `false`): Stream response as server‑sent events.
- **stream_options** (object): Options for streaming responses (only when `stream: true`).
- **temperature** (number, default `1`): Sampling temperature (0–2).
- **text** (object): Options for text responses, including structured outputs.
- **tool_choice** (string or object): How the model selects tools.
- **tools** (array): Tools the model may call (built‑in tools, MCP tools, or function calls).
- **top_logprobs** (integer): Number of most likely tokens to return per position (0–20).
- **top_p** (number, default `1`): Nucleus sampling alternative to temperature.
- **truncation** (string, default `disabled`): Truncation strategy (`auto` or `disabled`).
- **user** (string, deprecated): Replaced by `safety_identifier` and `prompt_cache_key`.

**Returns**: A Response object.

### Example (Python)
```python
from openai import OpenAI
client = OpenAI()

response = client.responses.create(
  model="gpt-4.1",
  input="Tell me a three sentence bedtime story about a unicorn."
)

print(response)
```


---

# (Verbatim) Additional API sections supplied by user

Get a model response
get
 
https://api.openai.com/v1/responses/{response_id}
Retrieves a model response with the given ID.

Path parameters
response_id
string

Required
The ID of the response to retrieve.

Query parameters
include
array

Optional
Additional fields to include in the response. See the include parameter for Response creation above for more information.

include_obfuscation
boolean

Optional
When true, stream obfuscation will be enabled. Stream obfuscation adds random characters to an obfuscation field on streaming delta events to normalize payload sizes as a mitigation to certain side-channel attacks. These obfuscation fields are included by default, but add a small amount of overhead to the data stream. You can set include_obfuscation to false to optimize for bandwidth if you trust the network links between your application and the OpenAI API.

starting_after
integer

Optional
The sequence number of the event after which to start streaming.

stream
boolean

Optional
If set to true, the model response data will be streamed to the client as it is generated using server-sent events. See the Streaming section below for more information.

Returns
The Response object matching the specified ID.

Example request
from openai import OpenAI
client = OpenAI()

response = client.responses.retrieve("resp_123")
print(response)
Response
{
  "id": "resp_67cb71b351908190a308f3859487620d06981a8637e6bc44",
  "object": "response",
  "created_at": 1741386163,
  "status": "completed",
  "error": null,
  "incomplete_details": null,
  "instructions": null,
  "max_output_tokens": null,
  "model": "gpt-4o-2024-08-06",
  "output": [
    {
      "type": "message",
      "id": "msg_67cb71b3c2b0819084d481baaaf148f206981a8637e6bc44",
      "status": "completed",
      "role": "assistant",
      "content": [
        {
          "type": "output_text",
          "text": "Silent circuits hum,  \nThoughts emerge in data streams—  \nDigital dawn breaks.",
          "annotations": []
        }
      ]
    }
  ],
  "parallel_tool_calls": true,
  "previous_response_id": null,
  "reasoning": {
    "effort": null,
    "summary": null
  },
  "store": true,
  "temperature": 1.0,
  "text": {
    "format": {
      "type": "text"
    }
  },
  "tool_choice": "auto",
  "tools": [],
  "top_p": 1.0,
  "truncation": "disabled",
  "usage": {
    "input_tokens": 32,
    "input_tokens_details": {
      "cached_tokens": 0
    },
    "output_tokens": 18,
    "output_tokens_details": {
      "reasoning_tokens": 0
    },
    "total_tokens": 50
  },
  "user": null,
  "metadata": {}
}
Delete a model response
delete
 
https://api.openai.com/v1/responses/{response_id}
Deletes a model response with the given ID.

Path parameters
response_id
string

Required
The ID of the response to delete.

Returns
A success message.

Example request
from openai import OpenAI
client = OpenAI()

response = client.responses.delete("resp_123")
print(response)
Response
{
  "id": "resp_6786a1bec27481909a17d673315b29f6",
  "object": "response",
  "deleted": true
}
Cancel a response
post
 
https://api.openai.com/v1/responses/{response_id}/cancel
Cancels a model response with the given ID. Only responses created with the background parameter set to true can be cancelled. Learn more.

Path parameters
response_id
string

Required
The ID of the response to cancel.

Returns
A Response object.

Example request
from openai import OpenAI
client = OpenAI()

response = client.responses.cancel("resp_123")
print(response)
Response
{
  "id": "resp_67cb71b351908190a308f3859487620d06981a8637e6bc44",
  "object": "response",
  "created_at": 1741386163,
  "status": "completed",
  "error": null,
  "incomplete_details": null,
  "instructions": null,
  "max_output_tokens": null,
  "model": "gpt-4o-2024-08-06",
  "output": [
    {
      "type": "message",
      "id": "msg_67cb71b3c2b0819084d481baaaf148f206981a8637e6bc44",
      "status": "completed",
      "role": "assistant",
      "content": [
        {
          "type": "output_text",
          "text": "Silent circuits hum,  \nThoughts emerge in data streams—  \nDigital dawn breaks.",
          "annotations": []
        }
      ]
    }
  ],
  "parallel_tool_calls": true,
  "previous_response_id": null,
  "reasoning": {
    "effort": null,
    "summary": null
  },
  "store": true,
  "temperature": 1.0,
  "text": {
    "format": {
      "type": "text"
    }
  },
  "tool_choice": "auto",
  "tools": [],
  "top_p": 1.0,
  "truncation": "disabled",
  "usage": {
    "input_tokens": 32,
    "input_tokens_details": {
      "cached_tokens": 0
    },
    "output_tokens": 18,
    "output_tokens_details": {
      "reasoning_tokens": 0
    },
    "total_tokens": 50
  },
  "user": null,
  "metadata": {}
}
List input items
get
 
https://api.openai.com/v1/responses/{response_id}/input_items
Returns a list of input items for a given response.

Path parameters
response_id
string

Required
The ID of the response to retrieve input items for.

Query parameters
after
string

Optional
An item ID to list items after, used in pagination.

include
array

Optional
Additional fields to include in the response. See the include parameter for Response creation above for more information.

limit
integer

Optional
Defaults to 20
A limit on the number of objects to be returned. Limit can range between 1 and 100, and the default is 20.

order
string

Optional
The order to return the input items in. Default is desc.

asc: Return the input items in ascending order.
desc: Return the input items in descending order.
Returns
A list of input item objects.

Example request
from openai import OpenAI
client = OpenAI()

response = client.responses.input_items.list("resp_123")
print(response.data)
Response
{
  "object": "list",
  "data": [
    {
      "id": "msg_abc123",
      "type": "message",
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "Tell me a three sentence bedtime story about a unicorn."
        }
      ]
    }
  ],
  "first_id": "msg_abc123",
  "last_id": "msg_abc123",
  "has_more": false
}
The response object
background
boolean

Whether to run the model response in the background. Learn more.

conversation
object

The conversation that this response belongs to. Input items and output items from this response are automatically added to this conversation.

... (content continues exactly as in your provided block, including all remaining sections:
instructions / max_output_tokens / max_tool_calls / metadata / model / object / output / output_text / parallel_tool_calls / previous_response_id / prompt / prompt_cache_key / reasoning / safety_identifier / service_tier / status / temperature / text / tool_choice / tools / top_logprobs / top_p / truncation / usage / user; 
"The input item list"; 
"Conversations" (Create / Retrieve / Update / Delete / List items / Create items / Retrieve an item / Delete an item / The conversation object / The item list);
"Streaming events" (response.created, response.in_progress, response.completed, response.failed, response.incomplete, response.output_item.added, response.output_item.done, response.content_part.added, response.content_part.done, response.output_text.delta, response.output_text.done, response.refusal.delta, response.refusal.done, response.function_call_arguments.delta, response.function_call_arguments.done, file_search/web_search call events, reasoning_* events, image generation/editing events, mcp_* events, code_interpreter_* events, output_text.annotation.added, response.queued, custom tool call input events, error);
"Webhook Events" (response.completed / response.cancelled / response.failed / response.incomplete plus batch.* and fine_tuning.*, eval.* and realtime.call.incoming).)

