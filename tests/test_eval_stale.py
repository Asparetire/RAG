"""评测跑批僵尸行清理单测（2026-11-16 排查顺带发现：重启杀 daemon 线程后 running 永挂——
gen_model-20261116-145758 卡 0/100 实证）。fake 连接，断言 SQL 而非真连库（同 test_paper_trash 范式）。"""

from __future__ import annotations

from doclens.eval import ablation


class FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, args=None):
        self._conn.queries.append((" ".join(sql.split()), args))
        self.rowcount = self._conn.rowcount
        return self.rowcount  # pymysql.Cursor.execute 语义：返回受影响行数


class FakeConn:
    def __init__(self, rowcount=1):
        self.queries = []
        self.rowcount = rowcount
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def test_sweep_stale_runs_updates_running_rows(monkeypatch):
    """启动清理：running → error + 中断说明；返回受影响行数。"""
    conn = FakeConn(rowcount=1)
    monkeypatch.setattr(ablation, "_conn", lambda: conn)
    n = ablation.sweep_stale_runs()
    assert n == 1
    assert len(conn.queries) == 1
    sql, args = conn.queries[0]
    assert sql.startswith("UPDATE t_eval_run SET status=%s")
    assert "WHERE status='running'" in sql
    assert args[0] == "error"
    assert "中断" in args[1]
    assert conn.commits == 1


def test_sweep_stale_runs_zero_rows(monkeypatch):
    """无遗留 running 行（正常重启）→ 返回 0、不抛错。"""
    conn = FakeConn(rowcount=0)
    monkeypatch.setattr(ablation, "_conn", lambda: conn)
    assert ablation.sweep_stale_runs() == 0
    assert conn.commits == 1
