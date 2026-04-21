# nano-bot-learn

一个用于学习 Python 和 `nanobot` 的最小仓库。

当前仓库的 Python 部分采用最小初始化：
- 用 `.venv/` 隔离项目本地环境
- 用 `pyproject.toml` 管理项目和开发依赖
- 用 `pytest` 跑测试
- 用 `ruff` 做静态检查

## 目录约定

- `nanobot_learn/`：当前学习包
- `tests/`：测试目录
- `docs/`：学习文档目录

## 首次初始化

第一次在这台机器上使用这个仓库时，执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
```

### 这些命令分别做什么

`python3 -m venv .venv`

为当前仓库创建一个本地虚拟环境。依赖会装到 `.venv/` 里，不会污染全局 Python。

`source .venv/bin/activate`

激活当前仓库的虚拟环境。激活之后，终端里的 `python`、`pip`、`pytest`、`ruff` 都会优先使用 `.venv` 里的版本。

`python -m pip install -e ".[dev]"`

把当前项目以可编辑模式安装到虚拟环境，并安装 `dev` 这组开发依赖。

- `-e` 表示 editable install。你修改本地源码后，不需要重新安装。
- `.` 表示当前目录这个项目。
- `.[dev]` 表示同时安装 `pyproject.toml` 里定义的开发依赖。

`python -m pytest -q`

运行测试。`-q` 是 quiet 模式，输出更精简。

`python -m ruff check .`

运行静态检查。`.` 表示检查当前仓库目录。

## 以后再次进入这个仓库

如果 `.venv/` 已经存在，通常只需要：

```bash
source .venv/bin/activate
python -m pytest -q
python -m ruff check .
```

一般不需要每次都重新执行 `python -m pip install -e ".[dev]"`。

只有在这些场景下，通常才需要重新安装：
- 你删掉了 `.venv/`
- 你换了机器
- `pyproject.toml` 里的依赖发生了变化

## 不想每次 `source`

也可以不激活环境，直接用 `.venv` 里的可执行文件：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
```

这种方式更显式，也更不容易误用全局 Python。
