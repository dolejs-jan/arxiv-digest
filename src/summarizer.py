from models import Paper, PaperSummary
from utils import save_summary_to_tmp, extract_text_from_pdf, call_with_retry


def split_text_into_chunks(text: str, max_chars: int = 10000, overlap_chars: int = 500) -> list[str]:
    """Split text into overlapping chunks by characters.

    This is a conservative, token-agnostic splitter that works well enough when
    a proper tokenizer (tiktoken) is not available in the environment.

    Args:
        text: The input text to split.
        max_chars: Approximate maximum number of characters per chunk.
        overlap_chars: Number of characters to overlap between consecutive chunks.

    Returns:
        List of text chunks.
    """
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = start + max_chars
        if end >= text_len:
            chunks.append(text[start:])
            break
        # try to cut at nearest newline or space to avoid breaking words
        cut = text.rfind('\n', start, end)
        if cut <= start:
            cut = text.rfind(' ', start, end)
        if cut <= start:
            cut = end
        chunk = text[start:cut]
        chunks.append(chunk)
        # advance with overlap
        start = max(cut - overlap_chars, cut)
    return chunks


def summarize_paper_with_chunking(paper: Paper, model_name: str, client) -> Paper:
    """Summarize a single paper, splitting long texts into chunks.

    Strategy:
    - If full paper text is small enough, send it directly and parse JSON response.
    - If too large, split into chunks, summarize each chunk to short plain text,
      then ask the model to combine the chunk summaries into the final JSON
      that matches PaperSummary.get_response_format().

    This keeps individual LLM requests under token limits while producing the
    same structured JSON output the rest of the code expects.
    """
    full_text = None
    pdf_url = paper.get_pdf_url()
    if pdf_url:
        print(f"    Fetching PDF: {pdf_url}")
        full_text = extract_text_from_pdf(pdf_url)

    if full_text:
        print("    Using full paper text for summarization (chunk-aware)")
        # Conservative character limit per chunk. Adjust if you know your model's
        # token/character ratio. 10k chars ~ ~2500 tokens roughly.
        max_chars = 10000
        chunks = split_text_into_chunks(full_text, max_chars=max_chars, overlap_chars=500)

        # If only one chunk, attempt original JSON prompt directly
        if len(chunks) == 1:
            content_section = f"Full Paper Text:\n{full_text}"
            prompt = f"""Summarize this research paper by extracting the following information.
Return a JSON object with exactly these fields:
- \"problem\": What problem is being addressed?
- \"proposed_method\": What approach or method is proposed?
- \"key_results\": What are the main findings and results?

Here is the paper content:
{content_section}
"""
            try:
                response = call_with_retry(lambda: client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are an expert researcher assistant. Provide concise and insightful summaries."},
                        {"role": "user", "content": prompt},
                    ],
                    model=model_name,
                    response_format=PaperSummary.get_response_format()
                ))

                paper.summary = PaperSummary.from_json(response.choices[0].message.content)
                save_summary_to_tmp(paper.to_dict(), paper.summary.to_json())
                return paper
            except Exception as e:
                # Fall through to chunked path on any error (including token limits)
                print(f"    Direct summarization failed, will try chunking: {e}")

        # Summarize each chunk into a short plain-text summary
        chunk_summaries = []
        for i, chunk in enumerate(chunks, start=1):
            short_prompt = f"Summarize this part of a research paper in 3 sentences focusing on the problem, the proposed method, and key results.\n\nPart {i} of {len(chunks)}:\n\n{chunk}\n\nShort summary:" 
            try:
                resp = call_with_retry(lambda: client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are an expert researcher assistant. Provide concise and focused summaries."},
                        {"role": "user", "content": short_prompt},
                    ],
                    model=model_name,
                    # We request plain text here (no structured response format)
                ))
                summary_text = resp.choices[0].message.content.strip()
                chunk_summaries.append(f"Part {i}: {summary_text}")
            except Exception as e:
                print(f"    Warning: chunk {i} summarization failed: {e}")
                # fallback: include a truncated snippet of the chunk so the final
                # summarization still has some content to work with
                snippet = chunk[:1000].rsplit('\n', 1)[0]
                chunk_summaries.append(f"Part {i}: [failed to summarize; inserting snippet]\n{snippet}")

        # Combine chunk summaries and ask the model for final structured JSON
        combined = "\n\n".join(chunk_summaries)
        final_prompt = f"""Combine the following short partial summaries of a research paper into one cohesive structured summary.\nReturn a JSON object with exactly these fields:\n- \"problem\": What problem is being addressed?\n- \"proposed_method\": What approach or method is proposed?\n- \"key_results\": What are the main findings and results?\n\nHere are the partial summaries:\n\n{combined}\n\nFinal structured summary (as JSON):"""
        try:
            final_resp = call_with_retry(lambda: client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert researcher assistant. Produce concise, factual, JSON-formatted summaries."},
                    {"role": "user", "content": final_prompt},
                ],
                model=model_name,
                response_format=PaperSummary.get_response_format()
            ))

            paper.summary = PaperSummary.from_json(final_resp.choices[0].message.content)
            save_summary_to_tmp(paper.to_dict(), paper.summary.to_json())
            return paper
        except Exception as e:
            print(f"    Error combining chunk summaries: {e}")
            paper.summary = PaperSummary.error(str(e))
            save_summary_to_tmp(paper.to_dict(), paper.summary.to_json())
            return paper

    else:
        # No full text available — fall back to abstract (existing behavior)
        content_section = f"\nTitle: {paper.title}\nAuthors: {', '.join(paper.authors)}\nAbstract: {paper.abstract}"
        print("    Falling back to abstract for summarization")
        prompt = f"""Summarize this research paper by extracting the following information.
Return a JSON object with exactly these fields:
- \"problem\": What problem is being addressed?
- \"proposed_method\": What approach or method is proposed?
- \"key_results\": What are the main findings and results?\n\nHere is the paper content:\n{content_section}\n"""
        try:
            response = call_with_retry(lambda: client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert researcher assistant. Provide concise and insightful summaries."},
                    {"role": "user", "content": prompt},
                ],
                model=model_name,
                response_format=PaperSummary.get_response_format()
            ))

            paper.summary = PaperSummary.from_json(response.choices[0].message.content)
            save_summary_to_tmp(paper.to_dict(), paper.summary.to_json())
            return paper
        except Exception as e:
            print(f"Error summarizing paper '{paper.title}': {e}")
            paper.summary = PaperSummary.error(str(e))
            save_summary_to_tmp(paper.to_dict(), paper.summary.to_json())
            return paper


def summarize_papers(papers: list[Paper], model_name, client) -> list[Paper]:
    print(f"Summarizing {len(papers)} papers...")

    for paper in papers:
        print(f"  Summarizing: {paper.title}")
        paper = summarize_paper_with_chunking(paper, model_name, client)

    return papers


if __name__ == "__main__":
    from openai import OpenAI
    from dotenv import load_dotenv
    from utils import load_config

    load_dotenv()
    config = load_config()

    summarize_model = config["models"]["summarize"]
    base_url = config["llm_service"]["base_url"]
    api_key = config["llm_service"]["api_key"]
    
    client = OpenAI(base_url=base_url, api_key=api_key)
    
    # Test with dummy data
    dummy_papers = [Paper(
        title="Test Paper",
        authors=["Author A", "Author B"],
        abstract="This is a test abstract about LLMs and agents.",
        link="https://arxiv.org/abs/2401.00001"
    )]
    try:
        summarized = summarize_papers(dummy_papers, summarize_model, client)
        print(summarized[0].summary)
    except Exception as e:
        print(f"Test failed: {e}")
