Vendored from https://github.com/zilliztech/GPTCache
Pinned commit: bae7ffeef774e762d9d4e60fce70be00011188a6 (tag 0.1.44, 2024-08-01)
Trimmed to setup.py, requirements.txt, README.md, LICENSE, and the gptcache/ package.
Docs, examples, tests, and the gptcache_server subpackage were dropped since this
project only imports the library, not the server or docs build.
Do not modify anything under gptcache/ after import; changes go through gptcache_ext/.
