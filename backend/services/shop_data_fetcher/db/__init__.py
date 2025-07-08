from abc import ABC, abstractmethod
from typing import Any, Tuple, List
from enum import Enum

class Keywords(Enum):
    SELECT = "SELECT"
    FROM = "FROM"
    JOIN = "JOIN"
    WHERE = "WHERE"
    ORDER_BY = "ORDER BY"
    LIMIT = "LIMIT"


class Condition:
    def __init__(self, sql: str, params: list):
        self.sql = sql
        self.params = params

    def __and__(self, other):
        return Condition(f"({self.sql}) AND ({other.sql})", self.params + other.params)

    def __or__(self, other):
        return Condition(f"({self.sql}) OR ({other.sql})", self.params + other.params)

    def __invert__(self):
        return Condition(f"NOT ({self.sql})", self.params)


class Field:
    def __init__(self, table: 'Table', name: str):
        self.table = table
        self.name = name

    def _expr(self, op: str, value):
        placeholder = "%s"
        return Condition(f"{self.table.alias}.{self.name} {op} {placeholder}", [value])

    def __eq__(self, other): return self._expr("=", other)
    def __ne__(self, other): return self._expr("<>", other)
    def __lt__(self, other): return self._expr("<", other)
    def __le__(self, other): return self._expr("<=", other)
    def __gt__(self, other): return self._expr(">", other)
    def __ge__(self, other): return self._expr(">=", other)

    def desc(self):
        return f"{self.table.alias}.{self.name} DESC"


class Table:
    _alias_counter = 0

    def __init__(self, name: str):
        self.name = name
        Table._alias_counter += 1
        self.alias = f"t{Table._alias_counter}"

    def __getitem__(self, col: str) -> Field:
        return Field(self, col)


class Query(ABC):
    def __init__(self):
        # Initialize an empty list for each clause keyword
        self.clauses = {kw: [] for kw in Keywords}

    def select(self, *fields: Field):
        self.clauses[Keywords.SELECT] = [f"{f.table.alias}.{f.name}" for f in fields]
        return self

    def from_(self, table: Table):
        self.clauses[Keywords.FROM] = [table]
        return self

    def join(self, table: Table, on: Condition):
        self.clauses[Keywords.JOIN].append((table, on))
        return self

    def where(self, *conditions: Condition):
        self.clauses[Keywords.WHERE].extend(conditions)
        return self

    def order_by(self, *orderings: str):
        self.clauses[Keywords.ORDER_BY] = list(orderings)
        return self

    def limit(self, count: int):
        self.clauses[Keywords.LIMIT] = [str(count)]
        return self

    def to_sql(self):
        parts = []
        params = []

        # SELECT clause
        select_vals = self.clauses[Keywords.SELECT]
        if not select_vals:
            raise ValueError('SELECT clause is required')
        parts.append(f"{Keywords.SELECT.value} {', '.join(select_vals)}")

        # FROM clause
        from_vals = self.clauses[Keywords.FROM]
        if not from_vals:
            raise ValueError('FROM clause is required')
        tbl = from_vals[0]
        parts.append(f"{Keywords.FROM.value} {tbl.name} AS {tbl.alias}")

        # JOIN clauses
        for tbl, on in self.clauses[Keywords.JOIN]:
            parts.append(f"{Keywords.JOIN.value} {tbl.name} AS {tbl.alias} ON {on.sql}")
            params.extend(on.params)

        # WHERE clause
        where_vals = self.clauses[Keywords.WHERE]
        if where_vals:
            where_sql = ' AND '.join([c.sql for c in where_vals])
            parts.append(f"{Keywords.WHERE.value} {where_sql}")
            for c in where_vals:
                params.extend(c.params)

        # ORDER BY clause
        order_vals = self.clauses[Keywords.ORDER_BY]
        if order_vals:
            parts.append(f"{Keywords.ORDER_BY.value} {', '.join(order_vals)}")

        # LIMIT clause
        limit_vals = self.clauses[Keywords.LIMIT]
        if limit_vals:
            parts.append(f"{Keywords.LIMIT.value} %s")
            params.append(int(limit_vals[0]))

        return ' '.join(parts), params
