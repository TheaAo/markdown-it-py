Markdown is a lightweight markup language that uses simple plain-text syntax to represent structures such as headings, lists, links, and code blocks. This project is a Markdown parser that parses Markdown text into a token stream and renders it into HTML. It is based on CommonMark and also supports rule extensions and a plugin mechanism.

Basic syntax can be found at: https://commonmark.org/help/

## Task 1: Testing the Parsing and Rendering Functionality

In this task, you are asked to add `pytest` test cases for the parsing and rendering functionality to verify whether the Markdown parser complies with the CommonMark specification.

The following input files are already provided in the `/tests/test_cmark_spec` directory:

- `spec.md`
- `commonmark.json`
- `/test_spec/test_file.html`

Please implement the following test cases:

- `test_file()`

  Test the program’s parsing and rendering behavior on the complete specification file. Read the entire content of `spec.md`, render it to HTML using the CommonMark configuration, and compare the rendered output with the full content of `test_file.html`. This test can serve as an overall regression test.

- `test_spec()`

  Test the program’s parsing and rendering behavior against the CommonMark specification examples. Read the collection of test cases from `commonmark.json`. For each test case, extract the Markdown input and its corresponding expected HTML output, render the input, and compare the result with the expected output. Parameterized tests may be used to organize these checks.

If the results are semantically equivalent but differ slightly in serialization, such as whether the rendered output of an empty `blockquote` contains an internal newline, you may apply minimal normalization before comparison.


The following API can be helpful:

```python
# `MarkdownIt("commonmark")` creates a Markdown parser instance using the CommonMark preset.
# The parser will tokenize Markdown input and apply CommonMark-compliant parsing rules.
md = MarkdownIt("commonmark")

# `md.render(text)` parses the input Markdown string and renders it to an HTML string.
# It returns the final HTML output for the given Markdown content.
html = md.render(text)
```

## Task 2: Testing the Command-Line Interface

This project supports reading and parsing files through the command line, and then exiting. The normal exit code is `0`; if the program exits abnormally, it raises `SystemExit` with exit code `1`.

Please implement the following test cases:

- `test_parse_fail()`

  Test the program’s behavior when it cannot open an input file, for example, when the file path does not exist. In this case, the program should exit with an error and return the abnormal exit code.

- `test_non_utf8()`

  Test the program’s behavior when processing a Markdown file that is not encoded in UTF-8. The program should be able to handle such input and should not crash directly due to a decoding error.

- `test_multiple_files()`

  Test the program’s behavior when processing multiple input files in a single run. The program should output the corresponding parsed results in order and exit normally. The test inputs and expected outputs may be based on the Markdown content and corresponding HTML results in `commonmark.json`.

The following API can be helpful:

```python
# `parse.main(...)` is the CLI entry point of the parser.
# It takes a list of input file paths as arguments.
# Example:
parse.main(["/path/to/file.md"])
```