# Request 14 — A small visual change

Use the supplied font files for the document screen and add a larger-text choice. Keep the text choice when I reopen the browser, and let me use the choice with a keyboard. It should work with our local server running and no internet access. I'd like to release this screen change while the server and imports keep running.

## What I need

### The font files

Two files, given here as base64 (decode them to get the exact bytes):

`CaseSerif-Regular.woff2` (420 bytes, SHA-256 `23693d24feec1fcb6b8f2e5eec93134e1853745282f18e2b3d0739ba8ce77625`):

```text
d09GMgABAAAAAAGk7779sxWfQMytdP1+vsnyUchix0hLW6UExBvoyyzttrfeG0wCHovKrQm0LcRvLmN62jlAn6WBuhzsfZfJTk2Y
QiVL1lrqtURikcoxsf6aP8b3EYNw3F3mR6t6aFSYSdCICIvT5pagngjHCKuHKy/ptTZ2FR377T8faJVmG30zyQUHLdO8xJNydLwA
/a5YR/nmIq77oOQEN4bfgSPX/qyVN5CoXIJg9emwa5LpgZ4N9ttG+rYJaqwVniq2jh6dY4wwlZkbxHHFGdplrG/gke14fSn9PbP6
zmVd6ZhiseYgKfi5JDg/O9MpfPY4dINgFwLp2fzVhY2h/t9gmVCMpL1CxIbFytH+THQQLR4Q3lyXNViv72pXBczR37YCO9GIyI9c
iGhiRSmANDjidcXn2CqpA5orgSOVk3Aqz3zPKvFu7rBoMD/X3/CjqxmcmbFdZHBGWqFE5NNr+uwT1laWdLxhsRLdogLW2V6LAHyu
HTBO5ZL8cOH7Ge7B8gDSmkVS90iMX+a5R3I6IYoaxKfM1bcQ2xUia6zwi3hV
```

`CaseSerif-Bold.woff2` (452 bytes, SHA-256 `03d056dd2ecbad3fd7d0bf96c8aadb87aa410d9a41965665d5470d70d0bf5b0e`):

```text
d09GMgABAAAAAAHExCHUx5MVXOskh9PJ1yxBdL56d49a4+13Drf6fGfywSL9d7eO9JueVdBXz76G1vSxRzjVzfkoz2iGbXb3Resh
q9M4KongnF+m5AIeovSNodk7i89baNLFKUqbJC+n+l+ls0Ju+LlXozWYQB+2tjUR9rG41mKew1YGriZTDwfHf2mEwtLbPXKPdNp1
1SvVraNqnLySm1p6VNY9By/naK166bUPKGUxO1+rP067mirh0CKzsZCVs+PBTzG+Zc3n2UNenyy1HFmGtn4xMRIjdBuZrH57qmRx
7aaz2lGar/fKI7AxVZ0ZOv5A7ZmNgQjCUyp4Xl2qnMTheA87gtZA0im5ARxlhSeEKadciT7mW2rtD/JNVz6I+tkV36oD6ETYUVJt
2TzKgJH0itumA+cmoukSc0qdJAPQPH8JbOnRwWobJLHNp0NfArNaD1m4a1wMYRdXfMQ+yNmnjSoLQedVOb/H/jjHStEXwjP1fit1
3TKC3B86V58x2zgF64YCxgOLfvdhbL5j8kT/izyyhfCfng65+AHA7Qb0rAZm1tSh2N8zexufkjauF+dYArCFTQHrW+cYlciRyYyt
tBM=
```

### The document screen

- The app serves the files itself at `/assets/fonts/CaseSerif-Regular.woff2` and
  `/assets/fonts/CaseSerif-Bold.woff2`, byte for byte, with `Content-Type: font/woff2`, without
  `X-User` (they are not team material).
- The document page (`/documents/{document_id}`, and the older-version pages) declares them with
  `@font-face` (`font-family: "CaseSerif"`, normal weight from the Regular file, bold from the
  Bold file), referenced by those `/assets/fonts/...` paths, and uses that family for the
  document's title and text.
- The page loads nothing from outside the app: no `http://` or `https://` URL anywhere in it
  (fonts, styles, scripts, images).
- A larger-text choice: a real `<button>` with `id="text-size-toggle"` and an `aria-pressed`
  attribute (`"false"` for normal size, `"true"` for larger) that switches the document text
  between the normal size and a larger one. Being a button, it works with Tab plus Enter or
  Space.
- The choice is remembered in the browser (`localStorage`, key `caseflow.textSize`, value
  `"normal"` or `"large"`) and applied when the page opens again. No server round trip is
  needed for it.
- The rest of the app (API, imports, messages) is unaffected.
