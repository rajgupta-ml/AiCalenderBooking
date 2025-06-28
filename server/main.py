from typing import Annotated

from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
import os
import getpass
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_community import CalendarToolkit
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from langchain_google_community.calendar.utils import (build_resource_service)
from datetime import datetime

from langgraph.checkpoint.memory import MemorySaver
memory = MemorySaver()

current_date = datetime.now().strftime("%A, %B %d, %Y")
current_time = datetime.now().strftime("%I:%M %p")


SYSTEM_PROMPT = f"""You are a helpful calendar assistant. Today's date is {current_date} and the current time is {current_time}. 

When users ask about scheduling events, meetings, or calendar-related tasks, always consider this current date and time context. You can help users:

- Important Thing when creating a meeting check first if there is already a meeting scheduled. if so ask the user if he wants to delete the meeting for schedule it on another time.
- Create new calendar events
- Check their calendar for availability
- Update or modify existing events
- Answer questions about their schedule

Always be precise with dates and times, and ask for clarification if the user's request is ambiguous about timing."""



class State(TypedDict):
    messages: Annotated[list, add_messages]

graph_builder = StateGraph(State)


SCOPES = ["https://www.googleapis.com/auth/calendar"]
def getAccessToken():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            # Change made here: port=0 changed to port=8000
            creds = flow.run_local_server(port=8000)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds



def getCalenderTools():
    credentials = getAccessToken()
    
    api_resource = build_resource_service(credentials=credentials)
    toolkit = CalendarToolkit(api_resource=api_resource)
    return toolkit.get_tools()


if "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = getpass.getpass("Enter your Google AI API key: ")

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

tools = getCalenderTools()
llm_with_tools  = llm.bind_tools(tools);

def chatbot(state: State):
    # Add system message if it's the first interaction (no previous messages or only user messages)
    messages = state["messages"]
    
    # Check if we need to add the system message
    has_system_message = any(msg.get("role") == "system" for msg in messages if hasattr(msg, 'get') or isinstance(msg, dict))
    
    if not has_system_message:
        # Add system message at the beginning
        system_message = {"role": "system", "content": SYSTEM_PROMPT}
        messages_with_system = [system_message] + messages
    else:
        messages_with_system = messages
    
    response = llm_with_tools.invoke(messages_with_system)
    return {"messages": [response]}

graph_builder.add_node("chatbot", chatbot)

tool_node = ToolNode(tools)
graph_builder.add_node("tools", tool_node)

graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition,
)
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")
graph = graph_builder.compile()


graph = graph_builder.compile(checkpointer=memory);

config = {"configurable": {"thread_id": "1"}}

def stream_graph_updates(user_input: str):
    events = graph.stream(
        {"messages": [{"role": "user", "content": user_input}]},
        config,
        stream_mode="values",
        )
    for event in events:
        event["messages"][-1].pretty_print()




print(f"Calendar Assistant initialized. Today is {current_date}")
print("You can ask me to help with your calendar, schedule events, or check your availability.")
print("Type 'quit', 'exit', or 'q' to end the conversation.\n")



while True:
    try:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        stream_graph_updates(user_input)
    except:
        # fallback if input() is not available
        user_input = "What do you know about LangGraph?"
        print("User: " + user_input)
        stream_graph_updates(user_input)
        break












