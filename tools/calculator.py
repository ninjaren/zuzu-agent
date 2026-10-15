import ast
import math
import operator

# 允許的運算子節點（白名單）
_OPERATORS = {
    ast.Add:      operator.add,
    ast.Sub:      operator.sub,
    ast.Mult:     operator.mul,
    ast.Div:      operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod:      operator.mod,
    ast.Pow:      operator.pow,
    ast.USub:     operator.neg,   # 負號 -x
    ast.UAdd:     operator.pos,   # 正號 +x
}

# 允許的數學函式（白名單）
_FUNCTIONS = {
    "abs":    abs,
    "round":  round,
    "int":    int,
    "float":  float,
    "sqrt":   math.sqrt,
    "log":    math.log,
    "log2":   math.log2,
    "log10":  math.log10,
    "exp":    math.exp,
    "sin":    math.sin,
    "cos":    math.cos,
    "tan":    math.tan,
    "asin":   math.asin,
    "acos":   math.acos,
    "atan":   math.atan,
    "ceil":   math.ceil,
    "floor":  math.floor,
    "factorial": math.factorial,
}

# 允許的常數
_CONSTANTS = {
    "pi": math.pi,
    "e":  math.e,
    "tau": math.tau,
    "inf": math.inf,
}


def _eval_node(node):
    # 遞迴求值，只接受白名單內的節點類型，拒絕任何程式碼執行
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"不支援的常數類型：{type(node.value)}")

    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise ValueError(f"未知變數：{node.id}")

    if isinstance(node, ast.BinOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支援的運算子：{type(node.op).__name__}")
        left  = _eval_node(node.left)
        right = _eval_node(node.right)
        # 防止除以零
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise ZeroDivisionError("除以零")
        return op(left, right)

    if isinstance(node, ast.UnaryOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支援的一元運算子：{type(node.op).__name__}")
        return op(_eval_node(node.operand))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("不支援的函式呼叫形式")
        fn = _FUNCTIONS.get(node.func.id)
        if fn is None:
            raise ValueError(f"不支援的函式：{node.func.id}")
        args = [_eval_node(a) for a in node.args]
        return fn(*args)

    raise ValueError(f"不允許的語法節點：{type(node).__name__}")


def calculate(expression: str) -> str:
    # 安全計算數學表達式，不執行任何程式碼（使用 AST 白名單解析）
    # 支援：+ - * / // % **、sqrt/log/sin/cos 等函式、pi/e 常數
    expr = expression.strip()
    if not expr:
        return "請提供要計算的數學表達式"
    try:
        tree = ast.parse(expr, mode="eval")
        result = _eval_node(tree.body)
        # 整數結果去掉小數點，浮點數最多顯示 10 位有效數字
        if isinstance(result, float) and result.is_integer():
            return f"{expr} = {int(result)}"
        if isinstance(result, float):
            # 移除尾端多餘的零
            formatted = f"{result:.10g}"
            return f"{expr} = {formatted}"
        return f"{expr} = {result}"
    except ZeroDivisionError:
        return "計算錯誤：除以零"
    except ValueError as e:
        return f"不支援的語法：{e}"
    except SyntaxError:
        return f"表達式語法錯誤：{expr}"
    except OverflowError:
        return "計算結果超出數值範圍"
    except Exception as e:
        return f"計算失敗：{e}"


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "安全計算數學表達式。支援加減乘除（+ - * / // %）、次方（**）、"
                "sqrt / log / log10 / sin / cos / tan / ceil / floor / factorial / abs / round，"
                "以及常數 pi、e。適合需要精確數值計算的場合，避免模型自行計算的誤差。"
                "範例：2**10、sqrt(144)、sin(pi/6)、log(100, 10)、factorial(10)"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "數學表達式，例如：(100 + 200) * 1.05、sqrt(2)、log(1000, 10)",
                    },
                },
                "required": ["expression"],
            },
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "calculate": calculate,
}
