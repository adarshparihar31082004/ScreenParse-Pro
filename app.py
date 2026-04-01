from __future__ import annotations

import io
import re
from pathlib import Path

import cv2
import numpy as np
import pytesseract
import streamlit as st
from PIL import Image


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

# Uncomment and adjust this on Windows if Tesseract is not in PATH.
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

ERROR_PATTERNS: dict[str, list[str]] = {
    "Authentication / Authorization": [
        r"\b401\b",
        r"\b403\b",
        r"unauthorized",
        r"forbidden",
        r"invalid token",
        r"authentication failed",
        r"access denied",
        r"permission denied",
    ],
    "Network / Connectivity": [
        r"timeout",
        r"connection refused",
        r"connection reset",
        r"host unreachable",
        r"network error",
        r"dns",
        r"socket",
        r"timed out",
    ],
    "Backend / Server": [
        r"\b500\b",
        r"\b502\b",
        r"\b503\b",
        r"\b504\b",
        r"internal server error",
        r"traceback",
        r"exception",
        r"server error",
    ],
    "Database": [
        r"sql",
        r"database",
        r"db error",
        r"constraint failed",
        r"unique constraint",
        r"foreign key",
        r"sqlite",
        r"no such table",
    ],
    "Frontend / Client": [
        r"undefined",
        r"typeerror",
        r"referenceerror",
        r"cannot read property",
        r"javascript",
        r"angular error",
        r"react error",
    ],
}


# ------------------------------------------------------------
# OCR + ANALYSIS LOGIC
# ------------------------------------------------------------

def preprocess_image(image: Image.Image) -> np.ndarray:
    """
    Convert a PIL image to a cleaner OpenCV representation
    to improve OCR extraction quality.
    """
    image_np = np.array(image)
    gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)

    denoised = cv2.GaussianBlur(gray, (3, 3), 0)

    processed = cv2.threshold(
        denoised,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )[1]

    return processed


def clean_text(text: str) -> str:
    """
    Normalize OCR output by removing excessive spaces and blank lines.
    """
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_image(image: Image.Image) -> str:
    """
    Run OCR on the preprocessed image.
    """
    processed = preprocess_image(image)
    raw_text: str = pytesseract.image_to_string(processed, lang="eng")
    return clean_text(raw_text)


def analyze_text(text: str) -> dict[str, str | list[str] | int]:
    """
    Detect likely engineering issue category using regex pattern matches.
    """
    normalized_text = text.lower()

    best_category = "General / Unknown"
    best_keywords: list[str] = []
    best_score = 0

    for category, patterns in ERROR_PATTERNS.items():
        current_matches: list[str] = []

        for pattern in patterns:
            matches = re.findall(pattern, normalized_text, flags=re.IGNORECASE)
            if matches:
                current_matches.extend(matches)

        score = len(current_matches)
        if score > best_score:
            best_score = score
            best_category = category
            best_keywords = sorted(set(current_matches))

    probable_cause_map: dict[str, str] = {
        "Authentication / Authorization": (
            "Likely invalid credentials, expired token, access-control issue, or missing permissions."
        ),
        "Network / Connectivity": (
            "Likely network timeout, DNS resolution failure, service unreachable state, or socket connectivity issue."
        ),
        "Backend / Server": (
            "Likely unhandled exception, dependency failure, unstable backend service, or server-side processing issue."
        ),
        "Database": (
            "Likely query failure, schema mismatch, constraint violation, or database connectivity issue."
        ),
        "Frontend / Client": (
            "Likely client-side runtime error, undefined variable, broken state handling, or bad API response usage."
        ),
        "General / Unknown": (
            "No strong error pattern detected. The screenshot may contain generic text or OCR may not have captured enough signal."
        ),
    }

    return {
        "category": best_category,
        "keywords": best_keywords,
        "score": best_score,
        "probable_cause": probable_cause_map[best_category],
    }


def get_next_steps(category: str) -> list[str]:
    """
    Return actionable debugging suggestions based on detected issue category.
    """
    next_steps_map: dict[str, list[str]] = {
        "Authentication / Authorization": [
            "Verify username, password, token, or API key.",
            "Check token expiry and refresh flow.",
            "Confirm user role or permission mappings.",
            "Inspect auth headers being sent by the client.",
            "Review backend access-control rules.",
        ],
        "Network / Connectivity": [
            "Check whether the target host and port are reachable.",
            "Verify DNS resolution and base URL correctness.",
            "Inspect timeout, retry, proxy, or VPN settings.",
            "Test the endpoint manually using curl or Postman.",
            "Check firewall or security-group restrictions.",
        ],
        "Backend / Server": [
            "Inspect server logs around the failure timestamp.",
            "Trace the failing code path or stack trace.",
            "Check upstream dependencies and service health.",
            "Validate request payload and backend assumptions.",
            "Look for recent deployments or config changes.",
        ],
        "Database": [
            "Verify database connection string and credentials.",
            "Check whether migrations ran successfully.",
            "Inspect schema, table, or column existence.",
            "Review constraint violations or duplicate keys.",
            "Test the failing query directly on the database.",
        ],
        "Frontend / Client": [
            "Inspect browser console and network tab.",
            "Check for undefined variables or bad state updates.",
            "Validate API response shape against frontend expectations.",
            "Review recent UI code changes and event handlers.",
            "Reproduce the issue with minimal user flow.",
        ],
        "General / Unknown": [
            "Try a clearer or higher-resolution screenshot.",
            "Check if OCR missed important text.",
            "Review the screenshot manually for context clues.",
            "Look for timestamps, status codes, or visible keywords.",
            "Consider expanding detection rules for this case.",
        ],
    }
    return next_steps_map.get(category, next_steps_map["General / Unknown"])


def generate_report(extracted_text: str, analysis: dict[str, str | list[str] | int]) -> str:
    """
    Create a downloadable plain-text report.
    """
    keywords = analysis["keywords"]
    keyword_text = ", ".join(keywords) if isinstance(keywords, list) and keywords else "None detected"

    category = str(analysis["category"])
    next_steps = get_next_steps(category)
    next_steps_block = "\n".join(f"- {step}" for step in next_steps)

    report = f"""
SCREENPARSE PRO REPORT
======================

CATEGORY:
{category}

MATCH SCORE:
{analysis["score"]}

PROBABLE CAUSE:
{analysis["probable_cause"]}

DETECTED KEYWORDS:
{keyword_text}

RECOMMENDED NEXT STEPS:
{next_steps_block}

EXTRACTED TEXT:
---------------
{extracted_text}
""".strip()

    return report


def save_report(filename_stem: str, content: str) -> Path:
    """
    Save the analysis report to outputs/ directory.
    """
    output_path = OUTPUT_DIR / f"{filename_stem}_analysis.txt"
    output_path.write_text(content, encoding="utf-8")
    return output_path


# ------------------------------------------------------------
# STREAMLIT UI
# ------------------------------------------------------------

st.set_page_config(
    page_title="ScreenParse Pro",
    page_icon="🧠",
    layout="centered",
)

st.title("ScreenParse Pro")
st.caption("Extract text from screenshots and classify likely engineering issues")

uploaded_file = st.file_uploader(
    "Upload a screenshot",
    type=["png", "jpg", "jpeg", "webp"],
)

if uploaded_file is not None:
    image_bytes: bytes = uploaded_file.read()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    st.image(image, caption="Uploaded Screenshot", use_container_width=True)

    if st.button("Analyze Screenshot", use_container_width=True):
        try:
            with st.spinner("Running OCR and analysis..."):
                extracted_text = extract_text_from_image(image)
                analysis = analyze_text(extracted_text)
                report = generate_report(extracted_text, analysis)

            st.success("Analysis complete.")

            st.subheader("Extracted Text")
            st.text_area(
                "OCR Output",
                value=extracted_text if extracted_text else "No text detected.",
                height=220,
            )

            st.subheader("Analysis")
            st.write(f"**Category:** {analysis['category']}")
            st.write(f"**Match Score:** {analysis['score']}")
            st.write(f"**Probable Cause:** {analysis['probable_cause']}")

            keywords = analysis["keywords"]
            if isinstance(keywords, list) and keywords:
                st.write("**Detected Keywords:**")
                for keyword in keywords:
                    st.markdown(f"- `{keyword}`")
            else:
                st.info("No strong error keywords detected.")

            next_steps = get_next_steps(str(analysis["category"]))

            st.subheader("Recommended Next Steps")
            for step in next_steps:
                st.markdown(f"- {step}")

            output_path = save_report(Path(uploaded_file.name).stem, report)

            with open(output_path, "rb") as file:
                st.download_button(
                    label="Download Analysis Report",
                    data=file,
                    file_name=output_path.name,
                    mime="text/plain",
                    use_container_width=True,
                )

        except pytesseract.pytesseract.TesseractNotFoundError:
            st.error(
                "Tesseract OCR is not installed or not found in PATH. "
                "Install Tesseract and set pytesseract.pytesseract.tesseract_cmd if needed."
            )
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")