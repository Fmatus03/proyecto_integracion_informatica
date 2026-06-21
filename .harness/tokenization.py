"""Token counting utilities backed by provider-compatible tokenizers."""
from pathlib import Path


def _encoding_for_model(model: str):
    try:
        import tiktoken
    except ImportError as exc:
        raise RuntimeError("tokenizer_unavailable:tiktoken") from exc

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str) -> int:
    encoding = _encoding_for_model(model)
    return len(encoding.encode(text))


def count_file_tokens(path: Path, model: str) -> int:
    return count_tokens(path.read_text(encoding="utf-8"), model)


def count_prompt_files(paths: dict, model: str) -> dict:
    return {
        label: count_file_tokens(Path(path), model)
        for label, path in paths.items()
    }
