from models import Paper, PaperSummary
from utils import save_summary_to_tmp, extract_text_from_pdf, call_with_retry


def summarize_papers(papers: list[Paper], model_name, client) -> list[Paper]:
    print(f"Summarizing {len(papers)} papers...")

    for paper in papers:
        print(f"  Summarizing: {paper.title}")
        
        # Try to get full paper text from PDF if available
        full_text = None
        pdf_url = paper.get_pdf_url()
        if pdf_url:
            print(f"    Fetching PDF: {pdf_url}")
            full_text = extract_text_from_pdf(pdf_url)
        
        # Use full text if available, otherwise fall back to abstract
        if full_text:
            content_section = f"Full Paper Text:\n{full_text}"
            print("    Using full paper text for summarization")
        else:
            content_section = f"""
Title: {paper.title}
Authors: {', '.join(paper.authors)}
Abstract: {paper.abstract}"""
            print("    Falling back to abstract for summarization")
        
        prompt = f"""Summarize this research paper by extracting the following information.
Return a JSON object with exactly these fields:
- "problem": What problem is being addressed?
- "proposed_method": What approach or method is proposed?
- "key_results": What are the main findings and results?

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
            
            # Save to tmp folder for inspection (local only)
            save_summary_to_tmp(paper.to_dict(), paper.summary.to_json())
            
        except Exception as e:
            print(f"Error summarizing paper '{paper.title}': {e}")
            paper.summary = PaperSummary.error(str(e))
            
            # Save error to tmp folder too
            save_summary_to_tmp(paper.to_dict(), paper.summary.to_json())

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
