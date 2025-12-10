"""LLM Setup for Agentic Workflows"""

#the main tools to integrate will be -> parse a list of cards, check validity, and add to collection
# create a listing based on the card description 
# scrap sold data from the website??

from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from dotenv import load_dotenv

load_dotenv()

@tool
def test_tool(input: str):
    """A tool to test the graph"""
    return f"The input is {input}"

@tool
def add(a: int, b: int):
    """ add two integers"""
    return a + b

@tool
def substract(a: int, b: int):
    """ substract b from a """
    return a - b

@tool
def add_to_collection(cards):
    """ Add a list of cards to the collection """
    return cards

search_tool = TavilySearch(max_results=5)


TOOLS = [test_tool, add, substract, add_to_collection, search_tool]

llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.1)
llm_with_tools = llm.bind_tools(TOOLS)