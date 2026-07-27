"""Embeds query text with GPTCache's default ONNX model, cached to disk by text hash
so reruns are cheap and deterministic.

Uses the tokenizer and model referenced by vendor/gptcache/gptcache/embedding/onnx.py
directly rather than importing that class, because its `encode_plus` call is not
available on the transformers version this project pins elsewhere (encode_plus was
removed; the modern tokenizer's `__call__` is the direct replacement but does not
emit `token_type_ids` for a fast tokenizer by default, so this module adds an
explicit all-zero token_type_ids array, standard for single-sequence input, matching
what encode_plus produced). vendor/gptcache is pinned and read-only, so this
compatibility fix lives here rather than there.
"""
import hashlib
import json
import os

import numpy as np

MODEL_REPO = "GPTCache/paraphrase-albert-onnx"
TOKENIZER_NAME = "GPTCache/paraphrase-albert-small-v2"


class OnnxEmbedder:
    """Loads the tokenizer and ONNX model once; call embed(text) or embed_many(texts)."""

    def __init__(self):
        from transformers import AutoConfig, AutoTokenizer
        from huggingface_hub import hf_hub_download
        import onnxruntime

        self.tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
        model_path = hf_hub_download(repo_id=MODEL_REPO, filename="model.onnx")
        self.session = onnxruntime.InferenceSession(model_path)
        self.dimension = AutoConfig.from_pretrained(TOKENIZER_NAME).hidden_size

    def embed(self, text: str) -> np.ndarray:
        encoded = self.tokenizer(text, padding="max_length")
        input_ids = np.array(encoded["input_ids"], dtype="int64").reshape(1, -1)
        attention_mask = np.array(encoded["attention_mask"], dtype="int64").reshape(1, -1)
        token_type_ids = np.zeros_like(input_ids)
        outputs = self.session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )
        token_embeddings = outputs[0]
        mask = (
            np.expand_dims(attention_mask, -1)
            .repeat(token_embeddings.shape[-1], -1)
            .astype(float)
        )
        sentence_emb = np.sum(token_embeddings * mask, 1) / np.maximum(mask.sum(1), 1e-9)
        return sentence_emb.flatten()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CachedEmbedder:
    """Wraps OnnxEmbedder with an on-disk cache keyed by sha256(text), so repeated
    runs over overlapping trace texts never re-embed a text already computed."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._embedder = None
        self._index_path = os.path.join(cache_dir, "index.json")
        self._index = self._load_index()

    def _load_index(self) -> dict:
        if os.path.exists(self._index_path):
            with open(self._index_path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_index(self) -> None:
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f)

    def _vec_path(self, digest: str) -> str:
        return os.path.join(self.cache_dir, f"{digest}.npy")

    def embed(self, text: str) -> np.ndarray:
        digest = _text_hash(text)
        vec_path = self._vec_path(digest)
        if digest in self._index and os.path.exists(vec_path):
            return np.load(vec_path)

        if self._embedder is None:
            self._embedder = OnnxEmbedder()
        vec = self._embedder.embed(text)
        np.save(vec_path, vec)
        self._index[digest] = True
        self._save_index()
        return vec

    def embed_many(self, texts) -> np.ndarray:
        return np.stack([self.embed(t) for t in texts])
