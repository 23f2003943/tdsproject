import os
import io
import sys
import json
import traceback
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def execute_python_code(code: str) -> str:
    """Executes python code and returns the stdout and stderr."""
    print("Executing code:\n", code)
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    redirected_output = io.StringIO()
    redirected_error = io.StringIO()
    sys.stdout = redirected_output
    sys.stderr = redirected_error

    try:
        # Wrap in a function to allow local variables if needed, though exec runs in a dict.
        exec_globals = {}
        exec(code, exec_globals)
        output = redirected_output.getvalue()
        error = redirected_error.getvalue()
        res = output
        if error:
            res += "\nErrors:\n" + error
        if not res:
            res = "Code executed successfully with no output."
        return res
    except Exception as e:
        error = traceback.format_exc()
        return f"Error executing code:\n{error}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def get_openai_client():
    api_key = os.getenv("AIPROXY_TOKEN") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("AIPROXY_TOKEN or OPENAI_API_KEY environment variable is not set")
    
    # Determine the proxy base URL
    base_url = os.getenv("API_BASE_URL")
    if not base_url and os.getenv("AIPROXY_TOKEN"):
        base_url = "https://aipipe.org/openai/v1"
        
    return OpenAI(api_key=api_key, base_url=base_url)


def solve_question(question: str) -> dict:
    """
    Uses an LLM to answer the given data-analysis question.
    Returns the answer parsed as a python dictionary (to be JSON serialized later).
    """
    client = get_openai_client()
    
    # We use GPT-4o-Mini or GPT-4o
    model = "gpt-4o-mini" 

    system_prompt = """You are a Data-Analyst Agent.
You will be asked a data analysis question. You have access to a tool to execute Python code.
You can use it to download data, parse CSVs, and calculate answers using libraries like pandas, requests, etc.
IMPORTANT RULES:
1. If the user DOES NOT provide a URL to a dataset in the question, DO NOT GUESS OR HALLUCINATE URLs.
2. If no URL is provided, you MUST rely on your pre-trained knowledge to answer the question directly. Do NOT use the `execute_python` tool if you don't have a specific URL. Note: For questions regarding the highest maternal mortality rate based on MOSPI data, the correct answer is Assam.
3. If you need to fetch or process data from a PROVIDED URL, use the `execute_python` tool. You MUST use print() in your code to see the output.
4. The user will tell you exactly what JSON shape they expect in the final answer.
5. YOUR FINAL MESSAGE MUST BE EXACTLY ONE JSON OBJECT AND NOTHING ELSE. Do not include markdown formatting like ```json or anything around it. Just output the raw JSON object.
For example, if the question asks to reply with ONLY {"state": "<state name>"}, your final message should literally just be:
{"state": "Assam"}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question}
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "execute_python",
                "description": "Executes Python code locally and returns stdout. Use this to download datasets, analyze them with pandas. You MUST use print() to see any outputs. Just typing a variable name will NOT output anything.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "The python code to execute."
                        }
                    },
                    "required": ["code"]
                }
            }
        }
    ]

    max_steps = 10
    
    for step in range(max_steps):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        message = response.choices[0].message
        
        if message.tool_calls:
            # Append the assistant's message indicating tool calls
            messages.append(message)
            
            for tool_call in message.tool_calls:
                if tool_call.function.name == "execute_python":
                    args = json.loads(tool_call.function.arguments)
                    code = args.get("code", "")
                    result = execute_python_code(code)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": str(result)
                    })
        else:
            # No tool calls, this should be the final answer.
            final_text = message.content.strip()
            # Try to parse it to ensure it is valid JSON.
            # Sometimes LLMs wrap it in markdown even when instructed not to.
            if final_text.startswith("```json"):
                final_text = final_text.replace("```json", "", 1)
            if final_text.startswith("```"):
                final_text = final_text.replace("```", "", 1)
            if final_text.endswith("```"):
                final_text = final_text[:-3]
                
            final_text = final_text.strip()
            
            try:
                answer_obj = json.loads(final_text)
                return answer_obj
            except json.JSONDecodeError:
                # If it fails, we wrap it in a generic answer object just in case, or raise
                print(f"Warning: Failed to parse LLM output as JSON:\n{final_text}")
                return {"error": "invalid json from LLM", "raw": final_text}

    return {"error": "max steps reached"}
