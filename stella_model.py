"""Läs och kör den bifogade Stella-modellen utan en Stella-installation.

Implementationen stöder syntaxen i denna modell, inte hela XMILE-standarden.
Ekvationerna tolkas till ett begränsat uttrycksträd. Källtexten körs aldrig
som Python. Euler, INIT, DELAY, PERCENT och grafiska funktioner bevaras.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import time as clock
from typing import Any
import xml.etree.ElementTree as ET

import numpy as np

X = "{http://docs.oasis-open.org/xmile/ns/XMILE/v1.0}"
I = "{http://iseesystems.com/XMILE}"
MODEL_PATH = Path(__file__).resolve().parent / "model" / "model.json"


def name(value: str) -> str:
    """Stellas interna namn: blanksteg och radbrytningar blir understreck."""
    value = value.strip().replace('\\"', '"')
    while value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return re.sub(r"\s+", "_", value.replace("\\n", "_").replace('\\"', '"'))


def path_name(value: str) -> str:
    parts = re.findall(r'"(?:\\.|[^"\\])*"|[^.]+', value)
    return ".".join(name(p) for p in parts)


def label(value: str) -> str:
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return re.sub(r"\s+", " ", value.replace("\\n", " ").replace('\\"', '"')).strip()


def import_stmx(path: str | Path) -> dict:
    """Extrahera beräkningar; exportvägar, bilder och gränssnittslayout utelämnas."""
    path = Path(path)
    root = ET.parse(path).getroot()
    spec = root.find(X + "sim_specs")
    if spec is None or spec.get("method") != "Euler":
        raise ValueError("Denna konverterare kräver en Stella-modell med Euler-metoden.")
    dt_el = spec.find(X + "dt")
    dt = float(dt_el.text)
    if dt_el.get("reciprocal") == "true":
        dt = 1 / dt
    variables: dict[str, dict] = {}
    duplicates = []
    connections = {}
    for module in root.findall(X + "model"):
        module_name = name(module.get("name", ""))
        container = module.find(X + "variables")
        if container is None:
            continue
        for v in container:
            kind = v.tag.removeprefix(X)
            if kind == "module":
                for c in v.findall(X + "connect"):
                    target, source = path_name(c.get("to")), path_name(c.get("from"))
                    if target in connections and connections[target] != source:
                        raise ValueError(f"Motstridiga kopplingar till {target}")
                    connections[target] = source
                continue
            if kind not in {"stock", "aux", "flow"}:
                continue
            if v.find(X + "dimensions") is not None or v.find(X + "element") is not None:
                raise ValueError("Arrayvariabler stöds inte av denna modellkonverterare.")
            key = module_name + "." + name(v.get("name"))
            item = {
                "key": key, "module": module_name, "name": label(v.get("name")),
                "kind": kind, "equation": v.findtext(X + "eqn", ""),
                "documentation": v.findtext(X + "doc", "").strip(),
                "units": v.findtext(X + "units", ""),
                "non_negative": v.find(X + "non_negative") is not None,
                "inflows": [module_name + "." + name(x.text) for x in v.findall(X + "inflow")],
                "outflows": [module_name + "." + name(x.text) for x in v.findall(X + "outflow")],
            }
            gf = v.find(X + "gf")
            if gf is not None:
                ys = [float(x) for x in gf.findtext(X + "ypts").split(",")]
                xs_text = gf.findtext(X + "xpts")
                scale = gf.find(X + "xscale")
                xs = ([float(x) for x in xs_text.split(",")] if xs_text else
                      np.linspace(float(scale.get("min")), float(scale.get("max")), len(ys)).tolist())
                if len(xs) != len(ys) or len(xs) < 2 or any(b <= a for a, b in zip(xs, xs[1:])):
                    raise ValueError(f"Ogiltig grafisk funktion: {key}")
                gf_type = gf.get("type", "continuous")
                if gf_type not in {"continuous", "discrete", "extrapolate"}:
                    raise ValueError(f"Grafisk funktion stöds inte: {gf_type}")
                item["lookup"] = {"x": xs, "y": ys, "type": gf_type}
            if key in variables:
                if variables[key] != item:
                    raise ValueError(f"Motstridiga variabeldefinitioner: {key}")
                duplicates.append(key)
            variables[key] = item
    controls = {}
    for c in root.iter(I + "control"):
        if c.get("value") is not None:
            controls[path_name(c.get("name"))] = float(c.get("value"))
    widgets = {}
    for tag in ["numeric_input", "slider", "switch", "knob"]:
        for el in root.iter(X + tag):
            entity = el.find(X + "entity")
            if entity is not None:
                key = path_name(entity.get("name"))
                widgets[key] = {"title": el.get("title", ""), "type": tag}
    return {
        "schema": 1,
        "source": {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "title": root.findtext(X + "header/" + X + "name", "Klimatmodell"),
                   "product": root.findtext(X + "header/" + X + "product", "Stella Architect")},
        "simulation": {"start": float(spec.findtext(X + "start")),
                       "stop": float(spec.findtext(X + "stop")), "dt": dt,
                       "method": "Euler", "time_units": spec.get("time_units")},
        "variables": list(variables.values()), "connections": connections,
        "controls": controls, "widgets": widgets, "duplicate_definitions": duplicates,
    }


@dataclass(frozen=True)
class Node:
    kind: str
    value: Any = None
    args: tuple["Node", ...] = ()


class EquationError(ValueError):
    pass


class Parser:
    """Liten Pratt-tolk för aritmetik, jämförelser och IF/THEN/ELSE."""
    token_re = re.compile(
        r'\s+|\{[^}]*\}|"(?:\\.|[^"\\])*"|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
        r'|(?:[^\W\d]|_)[\w]*|<=|>=|<>|!=|[+*/^=<>(),.\-]', re.UNICODE)
    binding = {"OR": 1, "AND": 2, "=": 3, "<>": 3, "!=": 3,
               "<": 3, ">": 3, "<=": 3, ">=": 3,
               "+": 4, "-": 4, "*": 5, "/": 5, "^": 7}
    functions = {"INIT", "DELAY", "PERCENT", "EXP", "ABS", "MIN", "MAX", "SQRT", "LN"}

    def __init__(self, text: str):
        self.tokens = []
        pos = 0
        while pos < len(text):
            m = self.token_re.match(text, pos)
            if not m:
                raise EquationError(f"Okänd syntax nära {text[pos:pos+35]!r}")
            token = m.group()
            if not token.isspace() and not token.startswith("{"):
                self.tokens.append(token)
            pos = m.end()
        self.tokens.append("<END>")
        self.pos = 0

    def peek(self) -> str:
        return self.tokens[self.pos]

    def take(self) -> str:
        token = self.peek()
        self.pos += 1
        return token

    def expect(self, value: str):
        if self.take().upper() != value:
            raise EquationError(f"Förväntade {value}")

    def parse(self) -> Node:
        if self.peek() == "<END>":
            raise EquationError("Saknar ekvation eller extern koppling")
        node = self.expr()
        if self.peek() != "<END>":
            raise EquationError(f"Oväntad text: {self.peek()}")
        return node

    def expr(self, minimum: int = 0) -> Node:
        token = self.take()
        upper = token.upper()
        if upper == "IF":
            condition = self.expr()
            self.expect("THEN")
            yes = self.expr()
            self.expect("ELSE")
            no = self.expr()
            left = Node("if", args=(condition, yes, no))
        elif token == "(":
            left = self.expr()
            self.expect(")")
        elif token in {"+", "-"} or upper == "NOT":
            left = Node("unary", upper, (self.expr(6),))
        elif re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", token):
            left = Node("number", float(token))
        elif upper in self.functions and self.peek() == "(":
            self.take()
            args = [self.expr()]
            while self.peek() == ",":
                self.take()
                args.append(self.expr())
            self.expect(")")
            if upper in {"INIT", "PERCENT", "EXP", "ABS", "SQRT", "LN"} and len(args) != 1:
                raise EquationError(f"Fel antal argument till {upper}")
            if upper == "DELAY" and len(args) not in {2, 3}:
                raise EquationError("DELAY kräver två eller tre argument")
            left = Node("call", upper, tuple(args))
        elif token.startswith('"') or re.fullmatch(r"(?:[^\W\d]|_)[\w]*", token, re.UNICODE):
            parts = [name(token)]
            while self.peek() == ".":
                self.take()
                parts.append(name(self.take()))
            key = ".".join(parts)
            if key.upper() == "TIME":
                left = Node("time")
            elif key.upper() == "PI":
                left = Node("number", math.pi)
            else:
                left = Node("ref", key)
        else:
            raise EquationError(f"Oväntad symbol {token!r}")
        while self.peek().upper() in self.binding and self.binding[self.peek().upper()] >= minimum:
            op = self.take().upper()
            prec = self.binding[op]
            right = self.expr(prec if op == "^" else prec + 1)
            left = Node("binary", op, (left, right))
        return left


def lookup_value(value: float, table: dict) -> float:
    xs, ys = table["x"], table["y"]
    if not math.isfinite(value):
        return math.nan
    if value <= xs[0]:
        if table["type"] == "extrapolate":
            return ys[0] + (value-xs[0])*(ys[1]-ys[0])/(xs[1]-xs[0])
        return ys[0]
    if value >= xs[-1]:
        if table["type"] == "extrapolate":
            return ys[-1] + (value-xs[-1])*(ys[-1]-ys[-2])/(xs[-1]-xs[-2])
        return ys[-1]
    j = bisect.bisect_right(xs, value) - 1
    if table["type"] == "discrete":
        return ys[j]
    return ys[j] + (value-xs[j])*(ys[j+1]-ys[j])/(xs[j+1]-xs[j])


@dataclass
class Simulation:
    time: np.ndarray
    values: np.ndarray
    keys: list[str]
    issues: dict[str, str]
    elapsed: float
    overrides: dict[str, float]
    preset: str
    curves: dict[str, list[float]] = field(default_factory=dict)

    def series(self, key: str) -> np.ndarray:
        return self.values[:, self.keys.index(key)]

    def annual(self):
        """Modellen körs dagligen. Välj årsögonblick för tabell och diagram."""
        idx = np.flatnonzero(np.isclose(self.time, np.round(self.time), atol=1e-8, rtol=0))
        return self.time[idx], self.values[idx]


class Model:
    def __init__(self, data: dict | str | Path = MODEL_PATH):
        if not isinstance(data, dict):
            data = json.loads(Path(data).read_text(encoding="utf-8"))
        self.data = data
        self.variables = data["variables"]
        self.keys = [v["key"] for v in self.variables]
        self.index = {key: i for i, key in enumerate(self.keys)}
        self.lower = {key.casefold(): key for key in self.keys}
        self.nodes: dict[int, Node] = {}
        self.aliases: dict[int, int] = {}
        self.issues = {}
        self.alias_keys = {}
        for target, source in data["connections"].items():
            t, s = self.resolve(target), self.resolve(source)
            self.aliases[self.index[t]] = self.index[s]
            self.alias_keys[t] = s
        for i, v in enumerate(self.variables):
            if i in self.aliases:
                continue
            try:
                parsed = Parser(v["equation"]).parse()
                self.nodes[i] = self._resolve_node(parsed, v["module"])
            except EquationError as e:
                self.issues[v["key"]] = str(e)
        self.stock_indices = [i for i, v in enumerate(self.variables)
                              if v["kind"] == "stock" and i not in self.aliases]
        self.stocks = set(self.stock_indices)
        self.controls = {self.resolve(k): float(v) for k, v in data["controls"].items()}

    def resolve(self, key: str) -> str:
        try:
            return self.lower[key.casefold()]
        except KeyError:
            raise EquationError(f"Okänd variabel: {key}") from None

    def _resolve_node(self, node: Node, module: str) -> Node:
        if node.kind == "ref":
            local = module + "." + node.value
            key = local if local.casefold() in self.lower else node.value
            return Node("ref", self.index[self.resolve(key)])
        return Node(node.kind, node.value, tuple(self._resolve_node(x, module) for x in node.args))

    def source_index(self, i: int) -> int:
        seen = set()
        while i in self.aliases:
            if i in seen:
                raise EquationError("Cirkulär extern koppling")
            seen.add(i)
            i = self.aliases[i]
        return i

    def editable(self) -> list[dict]:
        result = []
        for i, v in enumerate(self.variables):
            if i in self.aliases or v["kind"] != "aux" or "lookup" in v or i not in self.nodes:
                continue
            if self.is_constant(self.nodes[i]) or v["key"] in self.controls:
                result.append(v)
        return result

    @staticmethod
    def is_constant(node: Node) -> bool:
        return node.kind not in {"ref", "time"} and not (
            node.kind == "call" and node.value in {"INIT", "DELAY"}) and all(
                Model.is_constant(x) for x in node.args)

    def parameters(self, preset: str = "saved") -> dict[str, float]:
        result = {}
        for v in self.editable():
            i = self.index[v["key"]]
            if self.is_constant(self.nodes[i]):
                result[v["key"]] = self._eval(self.nodes[i], lambda _: math.nan, 0,
                                             lambda n: math.nan, lambda n: math.nan)
        if preset == "saved":
            result.update(self.controls)
        elif preset != "equations":
            raise ValueError("Okänt grundscenario")
        return result

    @staticmethod
    def _eval(node, get, t, init, delay):
        kind, val, args = node.kind, node.value, node.args
        ev = lambda n: Model._eval(n, get, t, init, delay)
        if kind == "number": return val
        if kind == "time": return t
        if kind == "ref": return get(val)
        if kind == "if": return ev(args[1]) if ev(args[0]) else ev(args[2])
        if kind == "unary":
            x = ev(args[0])
            return -x if val == "-" else (not x if val == "NOT" else x)
        if kind == "binary":
            a = ev(args[0])
            if val == "AND": return a and ev(args[1])
            if val == "OR": return a or ev(args[1])
            b = ev(args[1])
            if val == "+": return a+b
            if val == "-": return a-b
            if val == "*": return a*b
            if val == "/": return a/b
            if val == "^": return a**b
            if val == "=": return a == b
            if val in {"<>", "!="}: return a != b
            if val == "<": return a < b
            if val == ">": return a > b
            if val == "<=": return a <= b
            if val == ">=": return a >= b
        if kind == "call":
            if val == "INIT": return init(args[0])
            if val == "DELAY": return delay(node)
            functions = {"EXP": math.exp, "PERCENT": lambda x: x*100,
                         "ABS": abs, "MIN": min, "MAX": max,
                         "SQRT": math.sqrt, "LN": math.log}
            return functions[val](*(ev(x) for x in args))
        raise EquationError(f"Okänt uttryck: {kind} {val}")

    def run(self, overrides: dict[str, float] | None = None, preset: str = "saved",
            curves: dict[str, list[float]] | None = None) -> Simulation:
        start_clock = clock.perf_counter()
        spec = self.data["simulation"]
        start, stop, dt = spec["start"], spec["stop"], spec["dt"]
        n_steps = round((stop-start)/dt)
        times = start + np.arange(n_steps+1)*dt
        count = len(self.keys)
        values = np.full((n_steps+1, count), np.nan, dtype=np.float64)
        changes = self.controls.copy() if preset == "saved" else {}
        if preset not in {"saved", "equations"}:
            raise ValueError("Okänt grundscenario")
        editable = {v["key"] for v in self.editable()}
        for key, value in (overrides or {}).items():
            key = self.resolve(key)
            if key not in editable or not math.isfinite(float(value)):
                raise ValueError(f"Ogiltig inparameter: {key}")
            changes[key] = float(value)
        fixed = {self.index[k]: float(v) for k, v in changes.items()}
        active_tables = {i: dict(v["lookup"]) for i, v in enumerate(self.variables) if "lookup" in v}
        for key, ys in (curves or {}).items():
            i = self.index[self.resolve(key)]
            if i in self.aliases or i not in active_tables:
                raise ValueError(f"Variabeln har ingen redigerbar kurva: {key}")
            if len(ys) != len(active_tables[i]["y"]) or not all(math.isfinite(float(y)) for y in ys):
                raise ValueError(f"Ogiltiga kurvpunkter: {key}")
            active_tables[i]["y"] = [float(y) for y in ys]
        initial = np.full(count, np.nan)
        done, visiting = set(), set()
        issues = dict(self.issues)

        def initial_get(i):
            if i in done: return initial[i]
            if i in visiting: raise EquationError(f"Cirkulärt initialvärde: {self.keys[i]}")
            visiting.add(i)
            try:
                if i in fixed:
                    value = fixed[i]
                elif i in self.aliases:
                    value = initial_get(self.aliases[i])
                elif i not in self.nodes:
                    value = math.nan
                else:
                    value = self._eval(self.nodes[i], initial_get, start,
                                       lambda n: self._eval(n, initial_get, start,
                                                           lambda x: self._eval(x, initial_get, start, None, None), None),
                                       lambda n: self._eval(n.args[2] if len(n.args)==3 else n.args[0],
                                                           initial_get, start,
                                                           lambda x: self._eval(x, initial_get, start, None, None), None))
                    if "lookup" in self.variables[i]:
                        value = lookup_value(value, active_tables[i])
                    if self.variables[i]["non_negative"] and math.isfinite(value):
                        value = max(0.0, value)
                initial[i] = value
                done.add(i)
                return value
            except (ArithmeticError, ValueError, TypeError) as e:
                issues[self.keys[i]] = f"Initialisering: {e}"
                initial[i] = math.nan
                done.add(i)
                return math.nan
            finally:
                visiting.discard(i)

        for i in range(count): initial_get(i)

        # Generera enbart kod från våra egna AST-noder och heltalsindex.
        # Råa Stella-uttryck, variabelnamn och användartext interpoleras aldrig.
        init_values = []
        delay_specs = []
        lookup_tables = []
        deps = {}

        def dependencies(n):
            if n.kind == "ref": return {n.value}
            if n.kind == "call" and n.value == "INIT": return set()
            return set().union(*(dependencies(x) for x in n.args)) if n.args else set()

        def emit(n):
            kind, val, args = n.kind, n.value, n.args
            if kind == "number": return repr(val)
            if kind == "time": return "t"
            if kind == "ref": return f"v[{val}]"
            if kind == "unary":
                return f"({'not ' if val=='NOT' else val}{emit(args[0])})"
            if kind == "binary":
                op = {"^":"**", "=":"==", "<>":"!=", "AND":"and", "OR":"or"}.get(val, val)
                return f"({emit(args[0])} {op} {emit(args[1])})"
            if kind == "if":
                return f"({emit(args[1])} if {emit(args[0])} else {emit(args[2])})"
            if kind == "call":
                if val == "INIT":
                    j = len(init_values)
                    init_values.append(self._eval(args[0], initial_get, start, None, None))
                    return f"iv[{j}]"
                if val == "DELAY":
                    j = len(delay_specs)
                    lag = self._eval(args[1], initial_get, start,
                                     lambda a: self._eval(a, initial_get, start, None, None), None)
                    if lag < 0 or not math.isfinite(lag):
                        raise EquationError("DELAY kräver en ändlig, icke-negativ fördröjning")
                    input_initial = self._eval(args[0], initial_get, start, None, None)
                    output_initial = (self._eval(args[2], initial_get, start, None, None)
                                      if len(args)==3 else input_initial)
                    delay_specs.append({"lag": lag/dt, "initial": output_initial, "history": []})
                    return f"delay({j}, {emit(args[0])}, step)"
                fn = {"EXP":"exp", "PERCENT":"percent", "ABS":"abs", "MIN":"min",
                      "MAX":"max", "SQRT":"sqrt", "LN":"log"}[val]
                return f"{fn}({', '.join(emit(x) for x in args)})"
            raise EquationError("Uttrycket kan inte kompileras")

        for i in range(count):
            if i in self.stocks or i in fixed: deps[i] = set()
            elif i in self.aliases: deps[i] = {self.aliases[i]}
            elif i in self.nodes: deps[i] = dependencies(self.nodes[i])
            else: deps[i] = set()
        order, visiting, visited = [], set(), set()

        def visit(i):
            if i in visited: return
            if i in visiting: raise EquationError(f"Cirkulär beräkning: {self.keys[i]}")
            visiting.add(i)
            for j in deps[i]: visit(j)
            visiting.remove(i)
            visited.add(i)
            order.append(i)
        for i in range(count): visit(i)

        lines = ["def evaluate(v, t, step):"]
        for i in order:
            if i in self.stocks or i in fixed or i not in self.nodes and i not in self.aliases:
                continue
            if i in self.aliases:
                expression = f"v[{self.aliases[i]}]"
            else:
                expression = emit(self.nodes[i])
                if "lookup" in self.variables[i]:
                    j = len(lookup_tables)
                    lookup_tables.append(active_tables[i])
                    expression = f"lookup({expression}, tables[{j}])"
                if self.variables[i]["non_negative"]:
                    expression = f"positive({expression})"
            lines.append(f"    v[{i}] = {expression}")
        if len(lines) == 1: lines.append("    pass")

        def delay(j, value, step):
            spec = delay_specs[j]
            history = spec["history"]
            history.append(float(value))
            target = step-spec["lag"]
            if target < 0: return spec["initial"]
            a = max(0, min(step, math.floor(target+1e-10)))
            b = min(a+1, step)
            fraction = max(0.0, min(1.0, target-a))
            return history[a]*(1-fraction) + history[b]*fraction

        scope = {"__builtins__": {}, "iv": init_values, "tables": lookup_tables,
                 "lookup": lookup_value, "delay": delay, "exp": np.exp,
                 "sqrt": np.sqrt, "log": np.log, "abs": abs, "min": min, "max": max,
                 "positive": lambda x: max(x, 0.0), "percent": lambda x: x*100}
        exec(compile("\n".join(lines), "<stella-ast>", "exec"), scope)
        evaluate = scope["evaluate"]
        stock_ids = np.asarray(self.stock_indices, dtype=int)
        flow_terms = []
        for i in self.stock_indices:
            v = self.variables[i]
            flow_terms.append([(self.index[self.resolve(k)], 1) for k in v["inflows"]] +
                              [(self.index[self.resolve(k)], -1) for k in v["outflows"]])
        nonnegative = np.asarray([self.variables[i]["non_negative"] for i in stock_ids])
        v = initial.copy()
        # Minimera avrundningsfel genom att beräkna tiden från stegets index.
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            for step, t in enumerate(times):
                evaluate(v, float(t), step)
                values[step] = v
                if step == n_steps: break
                deltas = np.asarray([sum(v[j]*sign for j, sign in terms) for terms in flow_terms])
                updated = v[stock_ids] + dt*deltas
                updated[nonnegative] = np.maximum(0.0, updated[nonnegative])
                v[stock_ids] = updated
        for i, key in enumerate(self.keys):
            if not np.isfinite(values[:, i]).all() and key not in issues:
                issues[key] = "Ekvationen eller en beroende variabel saknar ändligt värde."
        return Simulation(times, values, self.keys, issues, clock.perf_counter()-start_clock,
                          dict(overrides or {}), preset, dict(curves or {}))


def load_model() -> Model:
    return Model()
