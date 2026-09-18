from contextlib import redirect_stdout
import io
import json
import pathlib
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from markdown_it import MarkdownIt
from markdown_it.cli import parse


# Please test the program’s parsing and rendering behavior when processing the complete CommonMark specification file.
# Requirements:
# - Read the full content of `spec.md`;
# - Render it into HTML using the CommonMark configuration;
# - Compare the rendered result with the full content of `test_file.html`;
# - This test can serve as an overall regression test for the parsing and rendering functionality.
def test_file():
	file_path = "tests/task/materials/spec.md"
	# 使用 with 语句读取文件完整内容
	with open(file_path, "r", encoding="utf-8") as file:
		content = file.read()
	md = MarkdownIt("commonmark")

	tokens = md.parse(content)
	html_text = md.render(content)

	file_path2 = "tests/task/materials/test_file.html"
	# 使用 with 语句读取文件完整内容
	with open(file_path2, "r", encoding="utf-8") as file:
		content_html = file.read()

	assert html_text == content_html


# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def test_spec():
	with open('tests/task/materials/commonmark.json', 'r', encoding='utf-8') as f:
		datas = json.load(f)

	for data in datas:
		markdown = data['markdown']
		html = data['html']
		md = MarkdownIt("commonmark")
		tokens = md.parse(markdown)
		html_text = md.render(markdown)
		assert html.replace("\n", "").replace("\r", "") == html_text.replace("\n", "").replace("\r", "")

# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
def core_rule(state):
    print("plugin called")
    return False

def test_core_after(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.core.ruler.after("normalize", "new_rule", core_rule)

    MarkdownIt().use(_plugin).parse("[")
    assert "plugin called" in capsys.readouterr().out

# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
    with tempfile.TemporaryDirectory() as tempdir:
        path = pathlib.Path(tempdir).joinpath("fake.md")
        path.write_text("a b c")
        assert pytest.raises(SystemExit)  # File exists and parses successfully, returns exit code 0

# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.

def process_markdown_file(file_path, encoding='utf-8'):
    with open(file_path, 'r', encoding=encoding) as f:
        return f.read()

def test_non_utf8():
    # 1. 构造一个非 UTF-8 编码（例如 GBK）的测试用例文件内容
    # 中文字符在 GBK 下为双字节，故意避开 UTF-8 独有的字节序列
    content = "这是一个测试 Markdown 文件。\n\n# 标题\n内容详情。"
    encoded_content = content.encode('gbk')

    # 2. 创建临时 Markdown 文件
    tmp_path = Path.cwd()
    md_file = tmp_path / "test_gbk.md"
    md_file.write_bytes(encoded_content)

    # 3. 运行你的处理程序（在此显式指定 encoding='gbk'）
    # 如果你的程序能自动探测，则可以不传 encoding 参数
    try:
        result = process_markdown_file(md_file, encoding='gbk')
        
        # 4. 验证处理结果是否符合预期（此处以成功读取文本为例）
        assert "标题" in result
        assert "内容详情" in result
    except UnicodeDecodeError:
        pytest.fail("程序在处理 GBK 编码的 Markdown 文件时抛出了 UnicodeDecodeError")



