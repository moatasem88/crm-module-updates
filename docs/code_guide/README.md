# Code guide builder

Regenerates `../custom-crm-updates-code-guide.html` from the app's current source
(code blocks are copied from the files, with their line numbers). The build
fails if a function in the new files is not shown in a step or not listed in
`REF` in `build.py`, so update the text there when you add one.

```bash
cd apps/custom_crm_updates/docs/code_guide
../../../../env/bin/python build.py ../custom-crm-updates-code-guide.html
```
