"""Janela semanal, deltas e ate tres acoes do relatorio de SEO."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from darkfac_mailer import (
    INSUFFICIENT_SAMPLE,
    Change,
    DimensionStat,
    PeriodStats,
    build_weekly_report,
    collect_weekly_report,
    render_report,
    week_windows,
)

SP = ZoneInfo("America/Sao_Paulo")


def at_sp(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=SP)


def _period(
    clicks: float,
    impressions: float,
    position: float | None = 5.0,
    pages: tuple[DimensionStat, ...] = (),
    queries: tuple[DimensionStat, ...] = (),
) -> PeriodStats:
    return PeriodStats(
        clicks=clicks,
        impressions=impressions,
        position=position,
        pages=pages,
        queries=queries,
    )


class WeekWindowTests(unittest.TestCase):
    def test_tuesday_uses_previous_monday_to_sunday(self) -> None:
        windows = week_windows(at_sp(2026, 11, 24, 9, 30))
        self.assertEqual(windows.current.start, date(2026, 11, 16))
        self.assertEqual(windows.current.end, date(2026, 11, 22))
        self.assertEqual(windows.previous.start, date(2026, 11, 9))
        self.assertEqual(windows.previous.end, date(2026, 11, 15))

    def test_monday_morning_uses_the_week_that_just_ended(self) -> None:
        windows = week_windows(at_sp(2026, 11, 23, 0, 0))
        self.assertEqual(windows.current.start, date(2026, 11, 16))
        self.assertEqual(windows.current.end, date(2026, 11, 22))
        self.assertEqual(windows.previous.start, date(2026, 11, 9))
        self.assertEqual(windows.previous.end, date(2026, 11, 15))

    def test_sunday_evening_does_not_close_the_current_week(self) -> None:
        windows = week_windows(at_sp(2026, 11, 22, 23, 59))
        self.assertEqual(windows.current.start, date(2026, 11, 9))
        self.assertEqual(windows.current.end, date(2026, 11, 15))
        self.assertEqual(windows.previous.start, date(2026, 11, 2))
        self.assertEqual(windows.previous.end, date(2026, 11, 8))

    def test_following_sunday_still_keeps_the_prior_complete_week(self) -> None:
        windows = week_windows(at_sp(2026, 11, 29, 18, 0))
        self.assertEqual(windows.current.start, date(2026, 11, 16))
        self.assertEqual(windows.current.end, date(2026, 11, 22))
        self.assertEqual(windows.previous.start, date(2026, 11, 9))
        self.assertEqual(windows.previous.end, date(2026, 11, 15))

    def test_next_monday_advances_one_civil_week(self) -> None:
        windows = week_windows(at_sp(2026, 11, 30, 0, 1))
        self.assertEqual(windows.current.start, date(2026, 11, 23))
        self.assertEqual(windows.current.end, date(2026, 11, 29))
        self.assertEqual(windows.previous.start, date(2026, 11, 16))
        self.assertEqual(windows.previous.end, date(2026, 11, 22))

    def test_windows_are_adjacent_monday_to_sunday(self) -> None:
        windows = week_windows(at_sp(2026, 11, 24))
        current = windows.current
        previous = windows.previous
        self.assertEqual(current.start.weekday(), 0)
        self.assertEqual(current.end.weekday(), 6)
        self.assertEqual(previous.start.weekday(), 0)
        self.assertEqual(previous.end.weekday(), 6)
        self.assertEqual((current.end - current.start).days + 1, 7)
        self.assertEqual((previous.end - previous.start).days + 1, 7)
        self.assertEqual(previous.end + timedelta(days=1), current.start)

    def test_sao_paulo_date_decides_the_boundary_not_utc(self) -> None:
        still_sunday_in_sp = datetime(2026, 11, 23, 2, 59, tzinfo=timezone.utc)
        already_monday_in_sp = datetime(2026, 11, 23, 3, 0, tzinfo=timezone.utc)
        before = week_windows(still_sunday_in_sp)
        after = week_windows(already_monday_in_sp)
        self.assertEqual(before.current.start, date(2026, 11, 9))
        self.assertEqual(before.current.end, date(2026, 11, 15))
        self.assertEqual(after.current.start, date(2026, 11, 16))
        self.assertEqual(after.current.end, date(2026, 11, 22))
        same_instant = at_sp(2026, 11, 23, 0, 0).astimezone(timezone.utc)
        self.assertEqual(week_windows(same_instant), after)

    def test_naive_datetime_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            week_windows(datetime(2026, 11, 24, 12, 0))


class MetricComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = at_sp(2026, 11, 24, 8, 0)

    def test_report_uses_the_same_windows(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=_period(1, 10),
            previous=_period(1, 10),
        )
        windows = week_windows(self.now)
        self.assertEqual(report.current_window, windows.current)
        self.assertEqual(report.previous_window, windows.previous)

    def test_clicks_and_impressions_show_value_previous_and_delta(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=_period(50, 1000, position=4),
            previous=_period(30, 800, position=8),
        )
        self.assertEqual(report.clicks.current, 50)
        self.assertEqual(report.clicks.previous, 30)
        self.assertEqual(report.clicks.delta, 20)
        self.assertIs(report.clicks.change, Change.MELHOROU)
        self.assertEqual(report.impressions.current, 1000)
        self.assertEqual(report.impressions.previous, 800)
        self.assertEqual(report.impressions.delta, 200)
        self.assertIs(report.impressions.change, Change.MELHOROU)

    def test_drop_in_clicks_and_impressions_is_worse(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=_period(10, 100, position=5),
            previous=_period(40, 500, position=5),
        )
        self.assertEqual(report.clicks.delta, -30)
        self.assertIs(report.clicks.change, Change.PIOROU)
        self.assertEqual(report.impressions.delta, -400)
        self.assertIs(report.impressions.change, Change.PIOROU)

    def test_ctr_delta_is_percentage_points(self) -> None:
        # 20/100 = 20%, 10/200 = 5%, delta = +15 pp.
        report = build_weekly_report(
            now=self.now,
            current=_period(20, 100, position=5),
            previous=_period(10, 200, position=5),
        )
        self.assertAlmostEqual(report.ctr.current, 20.0)
        self.assertAlmostEqual(report.ctr.previous, 5.0)
        self.assertAlmostEqual(report.ctr.delta, 15.0)
        self.assertIs(report.ctr.change, Change.MELHOROU)
        text = render_report(report)
        self.assertIn("delta +15.00 pp", text)
        self.assertIn("melhorou", text)

    def test_ctr_can_improve_while_clicks_fall(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=_period(8, 40, position=5),
            previous=_period(10, 100, position=5),
        )
        self.assertIs(report.clicks.change, Change.PIOROU)
        self.assertAlmostEqual(report.ctr.current, 20.0)
        self.assertAlmostEqual(report.ctr.previous, 10.0)
        self.assertAlmostEqual(report.ctr.delta, 10.0)
        self.assertIs(report.ctr.change, Change.MELHOROU)

    def test_ctr_decline_is_worse(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=_period(10, 100, position=5),
            previous=_period(10, 50, position=5),
        )
        self.assertAlmostEqual(report.ctr.delta, -10.0)
        self.assertIs(report.ctr.change, Change.PIOROU)
        self.assertIn("delta -10.00 pp", render_report(report))
        self.assertIn("piorou", render_report(report))

    def test_lower_average_position_is_improvement(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=_period(10, 100, position=4),
            previous=_period(10, 100, position=8),
        )
        self.assertEqual(report.position.current, 4)
        self.assertEqual(report.position.previous, 8)
        self.assertEqual(report.position.delta, -4)
        self.assertIs(report.position.change, Change.MELHOROU)
        text = render_report(report)
        self.assertIn("Posição média: atual 4.00, anterior 8.00, delta -4.00, melhorou", text)

    def test_higher_average_position_is_worse(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=_period(10, 100, position=12),
            previous=_period(10, 100, position=3),
        )
        self.assertEqual(report.position.delta, 9)
        self.assertIs(report.position.change, Change.PIOROU)
        self.assertIn("delta +9.00, piorou", render_report(report))

    def test_equal_values_are_stable(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=_period(10, 100, position=6),
            previous=_period(10, 100, position=6),
        )
        self.assertEqual(report.clicks.delta, 0)
        self.assertIs(report.clicks.change, Change.ESTAVEL)
        self.assertEqual(report.impressions.delta, 0)
        self.assertIs(report.impressions.change, Change.ESTAVEL)
        self.assertEqual(report.ctr.delta, 0)
        self.assertIs(report.ctr.change, Change.ESTAVEL)
        self.assertEqual(report.position.delta, 0)
        self.assertIs(report.position.change, Change.ESTAVEL)

    def test_render_names_the_sao_paulo_week(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=_period(50, 1000, position=4),
            previous=_period(30, 800, position=8),
        )
        text = render_report(report)
        self.assertIn("Semana atual: 2026-11-16 a 2026-11-22 (America/Sao_Paulo)", text)
        self.assertIn("Semana anterior: 2026-11-09 a 2026-11-15", text)
        self.assertIn("Cliques: atual 50, anterior 30, delta +20, melhorou", text)
        self.assertIn("Impressões: atual 1000, anterior 800, delta +200, melhorou", text)
        self.assertIn("CTR: atual 5.00%, anterior 3.75%, delta +1.25 pp, melhorou", text)


class ActionSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = at_sp(2026, 11, 24, 8, 0)

    def _report_from(self, current_parts, previous_parts) -> object:
        return build_weekly_report(
            now=self.now,
            current=_period(50, 1000, position=4, pages=current_parts[0], queries=current_parts[1]),
            previous=_period(80, 1200, position=5, pages=previous_parts[0], queries=previous_parts[1]),
        )

    def test_top_three_losses_mix_pages_and_queries(self) -> None:
        current_pages = (
            DimensionStat("https://example.test/a", clicks=40, impressions=400),
            DimensionStat("https://example.test/b", clicks=10, impressions=100),
            DimensionStat("https://example.test/c", clicks=50, impressions=100),
            DimensionStat("https://example.test/d", clicks=40, impressions=200),
        )
        previous_pages = (
            DimensionStat("https://example.test/a", clicks=100, impressions=800),
            DimensionStat("https://example.test/b", clicks=30, impressions=200),
            DimensionStat("https://example.test/c", clicks=10, impressions=50),
            DimensionStat("https://example.test/d", clicks=80, impressions=300),
        )
        current_queries = (
            DimensionStat("mansao", clicks=20, impressions=100),
            DimensionStat("piscina", clicks=4, impressions=40),
            DimensionStat("eventos", clicks=10, impressions=80),
        )
        previous_queries = (
            DimensionStat("mansao", clicks=70, impressions=200),
            DimensionStat("piscina", clicks=5, impressions=40),
            DimensionStat("eventos", clicks=10, impressions=70),
        )
        report = self._report_from(
            (current_pages, current_queries),
            (previous_pages, previous_queries),
        )
        chosen = [(action.kind, action.key, action.click_loss) for action in report.actions]
        self.assertEqual(
            chosen,
            [
                ("page", "https://example.test/a", 60),
                ("query", "mansao", 50),
                ("page", "https://example.test/d", 40),
            ],
        )
        self.assertLessEqual(len(report.actions), 3)
        self.assertIsNone(report.actions_message)
        self.assertIsNone(report.sample_message)
        self.assertEqual(
            report.actions[0].message,
            "Revisar página https://example.test/a: queda de 60 cliques (100 para 40).",
        )
        self.assertEqual(
            report.actions[1].message,
            'Revisar consulta "mansao": queda de 50 cliques (70 para 20).',
        )
        text = render_report(report)
        self.assertIn("1. Revisar página https://example.test/a", text)
        self.assertNotIn("example.test/b", text)
        self.assertNotIn("piscina", text)

    def test_ties_prefer_larger_impression_loss_then_page_then_key(self) -> None:
        current_pages = (
            DimensionStat("/b", clicks=10, impressions=40),
            DimensionStat("/a", clicks=20, impressions=100),
        )
        previous_pages = (
            DimensionStat("/b", clicks=20, impressions=50),
            DimensionStat("/a", clicks=30, impressions=500),
        )
        current_queries = (DimensionStat("z", clicks=5, impressions=100),)
        previous_queries = (DimensionStat("z", clicks=15, impressions=500),)
        report = self._report_from(
            (current_pages, current_queries),
            (previous_pages, previous_queries),
        )
        self.assertEqual(
            [(action.kind, action.key) for action in report.actions],
            [("page", "/a"), ("query", "z"), ("page", "/b")],
        )

    def test_same_loss_is_alphabetical_and_independent_of_input_order(self) -> None:
        forward_pages_now = (
            DimensionStat("/b", clicks=1, impressions=10),
            DimensionStat("/a", clicks=1, impressions=10),
        )
        forward_pages_before = (
            DimensionStat("/b", clicks=6, impressions=15),
            DimensionStat("/a", clicks=6, impressions=15),
        )
        reversed_pages_now = tuple(reversed(forward_pages_now))
        reversed_pages_before = tuple(reversed(forward_pages_before))
        first = self._report_from((forward_pages_now, ()), (forward_pages_before, ()))
        second = self._report_from((reversed_pages_now, ()), (reversed_pages_before, ()))
        self.assertEqual(
            [action.key for action in first.actions],
            [action.key for action in second.actions],
        )
        self.assertEqual([action.key for action in first.actions], ["/a", "/b"])

    def test_gains_and_flat_queries_are_not_actions(self) -> None:
        report = self._report_from(
            (
                (DimensionStat("/gain", clicks=100, impressions=100),),
                (DimensionStat("igual", clicks=4, impressions=10),),
            ),
            (
                (DimensionStat("/gain", clicks=1, impressions=10),),
                (DimensionStat("igual", clicks=4, impressions=20),),
            ),
        )
        self.assertEqual(report.actions, ())
        self.assertIsNone(report.actions_message)
        self.assertIn("Nenhuma queda de cliques em páginas ou consultas.", render_report(report))

    def test_page_missing_from_current_week_counts_as_total_loss(self) -> None:
        report = self._report_from(
            ((), ()),
            ((DimensionStat("/sumiu", clicks=12, impressions=30),), ()),
        )
        self.assertEqual(len(report.actions), 1)
        self.assertEqual(report.actions[0].key, "/sumiu")
        self.assertEqual(report.actions[0].click_loss, 12)

    def test_duplicate_keys_are_summed_before_ranking(self) -> None:
        report = self._report_from(
            (
                (
                    DimensionStat("/dup", clicks=1, impressions=1),
                    DimensionStat("/dup", clicks=1, impressions=1),
                ),
                (),
            ),
            (
                (
                    DimensionStat("/dup", clicks=5, impressions=5),
                    DimensionStat("/dup", clicks=5, impressions=5),
                ),
                (),
            ),
        )
        self.assertEqual(report.actions[0].click_loss, 8)


class InsufficientSampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = at_sp(2026, 11, 24, 8, 0)

    def test_none_periods_do_not_raise_and_report_insufficient_sample(self) -> None:
        report = build_weekly_report(now=self.now, current=None, previous=None)
        text = render_report(report)
        self.assertEqual(report.sample_message, INSUFFICIENT_SAMPLE)
        self.assertEqual(report.actions_message, INSUFFICIENT_SAMPLE)
        self.assertEqual(report.actions, ())
        for metric in (report.clicks, report.impressions, report.ctr, report.position):
            self.assertIs(metric.change, Change.AMOSTRA_INSUFICIENTE)
            self.assertIsNone(metric.current)
            self.assertIsNone(metric.delta)
        self.assertIn(INSUFFICIENT_SAMPLE, text)
        self.assertIn("America/Sao_Paulo", text)

    def test_measured_zeros_are_insufficient_without_exception(self) -> None:
        empty = PeriodStats(clicks=0, impressions=0, position=None)
        report = build_weekly_report(now=self.now, current=empty, previous=empty)
        self.assertEqual(report.sample_message, INSUFFICIENT_SAMPLE)
        self.assertIs(report.ctr.change, Change.AMOSTRA_INSUFICIENTE)
        self.assertIn(INSUFFICIENT_SAMPLE, render_report(report))

    def test_zero_impressions_do_not_divide_and_mark_rates(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=PeriodStats(clicks=5, impressions=0, position=4),
            previous=PeriodStats(clicks=1, impressions=0, position=9),
        )
        self.assertEqual(report.clicks.current, 5)
        self.assertEqual(report.clicks.previous, 1)
        self.assertEqual(report.clicks.delta, 4)
        self.assertIs(report.clicks.change, Change.MELHOROU)
        self.assertIs(report.ctr.change, Change.AMOSTRA_INSUFICIENTE)
        self.assertIsNone(report.ctr.delta)
        self.assertIs(report.position.change, Change.AMOSTRA_INSUFICIENTE)
        self.assertEqual(report.sample_message, INSUFFICIENT_SAMPLE)
        self.assertIn("CTR: amostra insuficiente", render_report(report))
        self.assertIn("Posição média: amostra insuficiente", render_report(report))

    def test_zero_rows_ask_for_a_sample_without_exception(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=_period(10, 100, position=4),
            previous=_period(8, 80, position=5),
        )
        self.assertEqual(report.actions, ())
        self.assertEqual(report.actions_message, INSUFFICIENT_SAMPLE)
        self.assertEqual(report.sample_message, INSUFFICIENT_SAMPLE)
        self.assertIs(report.clicks.change, Change.MELHOROU)
        self.assertIn("Ações recomendadas:\namostra insuficiente", render_report(report))

    def test_rows_with_only_zeros_do_not_raise(self) -> None:
        row = DimensionStat("/vazia", clicks=0, impressions=0)
        report = build_weekly_report(
            now=self.now,
            current=PeriodStats(clicks=0, impressions=0, pages=(row,)),
            previous=PeriodStats(clicks=0, impressions=0, queries=(DimensionStat("x", 0, 0),)),
        )
        self.assertEqual(report.actions, ())
        self.assertEqual(report.actions_message, INSUFFICIENT_SAMPLE)
        self.assertIn(INSUFFICIENT_SAMPLE, render_report(report))

    def test_click_loss_with_zero_impressions_still_ranks(self) -> None:
        report = build_weekly_report(
            now=self.now,
            current=PeriodStats(
                clicks=0,
                impressions=0,
                pages=(DimensionStat("/a", clicks=0, impressions=0),),
            ),
            previous=PeriodStats(
                clicks=5,
                impressions=0,
                pages=(DimensionStat("/a", clicks=5, impressions=0),),
            ),
        )
        self.assertEqual(len(report.actions), 1)
        self.assertEqual(report.actions[0].click_loss, 5)
        self.assertIs(report.ctr.change, Change.AMOSTRA_INSUFICIENTE)


class CollectTests(unittest.TestCase):
    def test_collect_fetches_the_two_civil_windows(self) -> None:
        calls: list[tuple[date, date]] = []

        class Source:
            def fetch_period(self, start: date, end: date) -> PeriodStats:
                calls.append((start, end))
                if start == date(2026, 11, 16):
                    return _period(15, 100, position=3)
                return _period(10, 80, position=6)

        report = collect_weekly_report(Source(), at_sp(2026, 11, 24, 7, 0))
        self.assertEqual(
            calls,
            [
                (date(2026, 11, 16), date(2026, 11, 22)),
                (date(2026, 11, 9), date(2026, 11, 15)),
            ],
        )
        self.assertEqual(report.clicks.delta, 5)
        self.assertIs(report.clicks.change, Change.MELHOROU)
        self.assertIs(report.position.change, Change.MELHOROU)


if __name__ == "__main__":
    unittest.main()
