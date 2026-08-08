# Baseline source map

Verifies every claim about GPTCache's baseline behavior (Section 2.2 of the report)
against the pinned GPTCache commit. This file is the source of truth for line references.

Pinned commit: `bae7ffeef774e762d9d4e60fce70be00011188a6` (tag `0.1.44`, vendored at
`vendor/gptcache/`).

## Claim 1: single global similarity threshold, default 0.8

`gptcache/config.py:40`

```python
similarity_threshold: float = 0.8,
```

No drift.

## Claim 2: hit decision logic

`gptcache/adapter/adapter.py:98-107` (threshold computed from `similarity_threshold`)
and `gptcache/adapter/adapter.py:173` (the comparison itself).

```python
# line 100
rank_threshold = (max_rank - min_rank) * similarity_threshold * cache_factor
```

```python
# line 173
if rank_threshold <= rank:
```

No drift.

## Claim 3: eviction is count-based only (LRU/LFU/FIFO/RR), no evicted metadata

`gptcache/manager/eviction/memory_cache.py:43-59`

```python
# line 44-53
if self._policy == "LRU":
    self._cache = cachetools.LRUCache(maxsize=maxsize, **kwargs)
elif self._policy == "LFU":
```

```python
# line 58-59
def put(self, objs: List[Any]):
    for obj in objs:
        self._cache[obj] = True
```

No drift. The `self._cache[obj] = True` line, which is what makes evicted-entry metadata
unavailable, sits at line 59 of this pinned version.

## Claim 4: `create_on`/`last_access` stored but never read

`gptcache/manager/scalar_data/base.py:70-71`

```python
# line 70-71
create_on: Optional[datetime] = None
last_access: Optional[datetime] = None
```

`gptcache/manager/scalar_data/sql_storage.py:64-65`

```python
# line 64-65
create_on = Column(DateTime, default=datetime.now)
last_access = Column(DateTime, default=datetime.now)
```

No drift. Note `last_access` is written on cache hit in several storage backends
(e.g. `sql_storage.py:287-288`, `mongo.py:243-244`) but is never read back into any
decision logic in `adapter.py` or the eviction policies. The "never read" claim holds for
decision logic specifically, not for the column being untouched.

## Claim 5: no admission control, every miss is inserted

`gptcache/adapter/adapter.py:258-273`

```python
# line 258-266
)(
    question,
    handled_llm_data,
    embedding_data,
    extra_param=context.get("save_func", None),
    session=session,
)
```

This is the unconditional `data_manager.save` call inside `update_cache_func`, reached
on every cache miss with no admission check. No drift.

## Claim 6: no cost accounting, no false-hit or stale-hit metrics, only op timers

`gptcache/report.py`

The `Report` class (lines 1-14) tracks only `OpCounter` totals per pipeline stage
(`op_pre`, `op_embedding`, `op_search`, `op_data`, `op_evaluation`, `op_post`, `op_llm`,
`op_save`) and a `hint_cache_count`. No field for regeneration cost, answer identity, or
validity. No drift.

## Summary

All six claims verified against the pinned commit, with no line-number drift. The one
clarification is on claim 4: `last_access` is written by storage backends on hit, just
never consumed by decision logic.
