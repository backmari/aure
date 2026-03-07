#!/usr/bin/env python3
"""
Test script to submit the prompt from test-prompt.md to the configured LLM
and print the raw response for debugging.

Usage:
    python test_prompt_submit.py [--prompt-file test-prompt.md]
"""

import argparse
import sys
import os


from langchain_core.messages import HumanMessage

# Ensure the project is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Load .env file (same as cli.py / mcp_server.py)
from dotenv import load_dotenv

load_dotenv()

from aure.llm import get_llm, get_llm_config, llm_available  # noqa: E402


def load_prompt(path: str) -> str:
    """Load prompt text from a markdown file.

    Strips leading/trailing whitespace. If the file is wrapped in a single
    markdown code fence (```), remove that wrapper so the LLM sees the raw
    prompt text.
    """
    with open(path, "r") as f:
        text = f.read().strip()

    # Strip outer markdown code fence if present
    if text.startswith("```") and text.endswith("```"):
        # Remove first line (```markdown or ```) and last line (```)
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()

    return text


def main():
    parser = argparse.ArgumentParser(
        description="Submit a prompt to the LLM for debugging"
    )
    parser.add_argument(
        "--prompt-file",
        default="test-prompt.md",
        help="Path to the markdown file containing the prompt (default: test-prompt.md)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="LLM temperature (default: 0.0)",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Print the prompt before sending",
    )
    args = parser.parse_args()

    # Check LLM availability
    if not llm_available():
        print("ERROR: LLM is not available. Check your LLM_PROVIDER / API key config.")
        sys.exit(1)

    # Show LLM info
    config = get_llm_config()
    print("=" * 60)
    print("LLM Configuration")
    print("=" * 60)
    print(f"  Provider:    {config['provider']}")
    print(f"  Model:       {config['model']}")
    print(f"  Temperature: {args.temperature}")
    print(f"  Base URL:    {config.get('base_url') or '(default)'}")
    print("=" * 60)

    # Load prompt
    prompt_text = load_prompt(args.prompt_file)
    print(f"\nLoaded prompt from: {args.prompt_file}")
    print(f"Prompt length: {len(prompt_text)} chars, {len(prompt_text.split())} words")

    if args.show_prompt:
        print("\n" + "-" * 60)
        print("PROMPT TEXT:")
        print("-" * 60)
        print(prompt_text)
        print("-" * 60)

    # Submit to LLM
    print("\nSending prompt to LLM...")
    llm = get_llm(temperature=args.temperature)

    try:
        response = llm.invoke([HumanMessage(content=prompt_text)])
    except Exception as e:
        print(f"\nERROR during LLM call: {type(e).__name__}: {e}")
        sys.exit(1)

    # Print response
    print("\n" + "=" * 60)
    print("LLM RESPONSE")
    print("=" * 60)
    print(response.content)
    print("=" * 60)

    # Quick validation check (same as _validate_model_script)
    required_strings = ["load4(", "SLD(", "sample =", "Experiment(", "FitProblem("]
    matches = sum(1 for s in required_strings if s in response.content)
    print(f"\nValidation: {matches}/{len(required_strings)} required strings found")
    if matches < 4:
        print("WARNING: Response would FAIL _validate_model_script() (needs >= 4)")
        print("This means the fallback (widen bounds) would be triggered.")
    else:
        print("OK: Response would PASS _validate_model_script()")

    # Check for refusal patterns
    refusal_patterns = [
        "I'm sorry",
        "I cannot",
        "I can't",
        "I apologize",
        "cannot fulfill",
        "can't fulfill",
        "not able to",
        "unable to",
    ]
    found_refusals = [
        p for p in refusal_patterns if p.lower() in response.content.lower()
    ]
    if found_refusals:
        print(f"\nWARNING: Detected refusal phrases: {found_refusals}")


if __name__ == "__main__":
    main()
