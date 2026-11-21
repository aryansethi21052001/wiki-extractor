import streamlit as st

from wikipedia_extractor_core import (
    WikipediaExtractor,
    format_txt,
    numbered_filename,
    safe_filename,
)

# ---------------------------------------------------------------------------
# Page configuration (must be the first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Wikipedia Extractor", layout="wide")

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
_DEFAULT_KEYS = {
    "topic": None,
    "article": None,
    "titles": [],
    "selected": [],
    "sections": [],
    "saved_path": None,
    "downloaded_filenames": [],
}

for _key, _default in _DEFAULT_KEYS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _default

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Controls")
    if st.button("Start Over"):
        for _key in list(st.session_state.keys()):
            del st.session_state[_key]
        st.rerun()

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
st.title("Wikipedia Article Extractor")

# How-to guide
with st.expander("How to use this app"):
    st.markdown(
        "1. Enter a topic in the search box below.\n"
        "2. Select the section(s) you want to extract.\n"
        "3. Click **Extract** to preview the content.\n"
        "4. Click **Download .txt** to save it to your computer."
    )

# Progress indicator
_progress_cols = st.columns(4)
_progress_cols[0].caption(
    f"{'✅' if st.session_state.topic else '⬜'} Search"
)
_progress_cols[1].caption(
    f"{'✅' if st.session_state.titles else '⬜'} Select"
)
_progress_cols[2].caption(
    f"{'✅' if st.session_state.sections else '⬜'} Extract"
)
_progress_cols[3].caption(
    f"{'✅' if st.session_state.saved_path else '⬜'} Download"
)

# 1. Search form
with st.form("search_form"):
    topic_input = st.text_input("Enter a topic")
    submitted = st.form_submit_button("Search")

# --- Stage 1: Search submit handler ---------------------------------------
if submitted:
    _stripped = topic_input.strip()
    if _stripped:
        st.session_state.topic = _stripped
        article = WikipediaExtractor(_stripped)
        st.session_state.article = article
        st.session_state.titles = []
        st.session_state.selected = []
        st.session_state.sections = []
        st.session_state.saved_path = None
        if article.error:
            st.error(article.error)
        elif article.title is None:
            st.warning("No article found for that topic.")
        else:
            st.success(f"Article found: {article.title}")
            st.write(article.url)
            st.session_state.titles = article.section_titles()

# 2. Article info placeholder
article_info_placeholder = st.container()

# --- Stage 2: Select -------------------------------------------------------
if (
    st.session_state.article is not None
    and st.session_state.article.title is not None
    and st.session_state.titles
):
    st.caption(
        "Each option is a top-level section. Selecting a section also "
        "includes its subsections (e.g. 'Geography' includes 'Climate', "
        "'Environment', 'Architecture')."
    )
    if "multiselect_key" not in st.session_state:
        st.session_state.multiselect_key = st.session_state.selected
    st.multiselect(
        "Sections to extract",
        options=st.session_state.titles,
        key="multiselect_key",
    )
    st.session_state.selected = st.session_state.multiselect_key
else:
    if "multiselect_key" in st.session_state:
        del st.session_state["multiselect_key"]

# 3. Section multiselect placeholder
section_select_placeholder = st.container()

# --- Stage 3: Extract ------------------------------------------------------
if st.button("Extract"):
    article = st.session_state.article
    if article is None or article.title is None:
        st.warning("Search for an article first.")
    elif not st.session_state.selected:
        st.warning("Please select at least one section.")
    else:
        st.session_state.sections = [
            article.extract(t) for t in st.session_state.selected
        ]

# 4. Extract button placeholder
extract_button_placeholder = st.container()

# --- Stage 4: Preview ------------------------------------------------------
if st.session_state.sections:
    with st.container(border=True):
        for section in st.session_state.sections:
            st.markdown(f"### {section['title']}")
            if not section["blocks"]:
                st.caption("(no extractable content)")
                continue
            for block in section["blocks"]:
                if block["type"] == "paragraph":
                    st.write(block["text"])
                elif block["type"] == "subheading":
                    st.markdown(
                        f"<div style='font-weight:600; font-size:1.05rem; "
                        f"color:#444;'>{block['text']}</div>",
                        unsafe_allow_html=True,
                    )
                elif block["type"] == "list":
                    marker = "1." if block["ordered"] else "-"
                    for item in block["items"]:
                        st.markdown(f"{marker} {item}")
                elif block["type"] == "table":
                    st.dataframe(block["rows"])

# 5. Preview placeholder
preview_placeholder = st.container()

# --- Stage 5: Download -----------------------------------------------------
if st.session_state.sections:
    article = st.session_state.article
    proposed_name = safe_filename(article.title) + ".txt"

    if proposed_name in st.session_state.downloaded_filenames:
        st.warning(
            "You already downloaded a file with this name in this "
            "session. Downloading again will add (2) to the name."
        )

    download_name = numbered_filename(
        proposed_name, st.session_state.downloaded_filenames
    )

    st.download_button(
        label="Download .txt",
        data=format_txt(
            article.title, article.url, st.session_state.sections
        ),
        file_name=download_name,
        mime="text/plain",
        key="download_btn",
        on_click="ignore",
    )

# 6. Save button placeholder
save_button_placeholder = st.container()

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.caption("Content from Wikipedia, CC BY-SA 4.0.")

# ---------------------------------------------------------------------------
# Debug: watch state change as you click around
# ---------------------------------------------------------------------------
st.write(st.session_state)