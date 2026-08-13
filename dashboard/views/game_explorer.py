from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.data import filter_games, load_game_proposals, load_table


COLORS = {"EXACT": "#538d4e", "PRESENT": "#b59f3b", "ABSENT": "#3a3a3c"}


def _choices(frame: pd.DataFrame, column: str) -> list[str]:
    return sorted(frame[column].dropna().astype(str).unique())


def _value(value, default=None):
    if value is None:
        return default
    if isinstance(value, (list, tuple)) or hasattr(value, "tolist"):
        return value
    return default if pd.isna(value) else value


def wordle_row(guess: str | None, feedback) -> str:
    word = str(_value(guess, "")).upper()[:5].ljust(5)
    labels = list(_value(feedback, []))
    tiles = []
    for index, letter in enumerate(word):
        label = labels[index] if index < len(labels) else None
        color = COLORS.get(label, "#121213")
        border = color if label else "#565758"
        tiles.append(
            f'<span title="{escape(str(label or "No feedback"))}" style="display:inline-flex;'
            f'align-items:center;justify-content:center;width:3.4rem;height:3.4rem;margin:.18rem;'
            f'background:{color};border:2px solid {border};color:white;font:700 1.75rem Arial">'
            f'{escape(letter)}</span>'
        )
    return '<div style="white-space:nowrap;text-align:center">' + "".join(tiles) + "</div>"


def _played_rows(trajectory: pd.DataFrame, through_round: int) -> pd.DataFrame:
    return trajectory.loc[(trajectory["top1_played"]) & (trajectory["decision_round"] <= through_round)]


def _round_states(trajectory: pd.DataFrame, through_round: int) -> list[tuple[int, object | None, str]]:
    states = []
    for decision_round in range(1, through_round + 1):
        proposals = trajectory.loc[trajectory["decision_round"] == decision_round]
        played = proposals.loc[proposals["top1_played"]]
        if not played.empty:
            row = next(played.itertuples(index=False))
            label = "played after repair" if row.proposal_type == "repair" else "played"
            states.append((decision_round, row, label))
        elif not proposals.empty:
            states.append((decision_round, next(proposals.itertuples(index=False)), "forfeited"))
    return states


def _proposal_table(row) -> pd.DataFrame:
    consistency = [_value(getattr(row, f"top{i}_constraint_consistent")) for i in range(1, 4)]
    return pd.DataFrame({
        "Rank": [1, 2, 3],
        "Guess": [_value(getattr(row, f"top{i}"), "—") for i in range(1, 4)],
        "Action valid": [bool(_value(getattr(row, f"top{i}_action_valid"), False)) for i in range(1, 4)],
        "Constraint consistent": ["—" if value is None else ("yes" if value else "no")
                                   for value in consistency],
        "Information gain": [_value(getattr(row, f"information_gain_top{i}"), None) for i in range(1, 4)],
    })


def _candidate_chart(played: pd.DataFrame) -> go.Figure:
    if played.empty:
        return go.Figure()
    x = [0, *played["decision_round"].astype(int).tolist()]
    y = [int(played.iloc[0]["candidate_count_before"]),
         *played["candidate_count_after"].astype(int).tolist()]
    figure = go.Figure(go.Scatter(x=x, y=y, mode="lines+markers", line_shape="hv"))
    figure.update_layout(height=260, margin=dict(l=20, r=20, t=35, b=20),
                         title="Feasible secrets", xaxis_title="Decision round",
                         yaxis_title="Candidates", yaxis_type="log")
    return figure


def _render_replay(game, trajectory: pd.DataFrame) -> None:
    rounds = sorted(trajectory["decision_round"].astype(int).unique())
    selected_round = st.select_slider("Replay through decision round", rounds, value=rounds[-1])
    played = _played_rows(trajectory, selected_round)
    states = _round_states(trajectory, selected_round)

    header = st.columns([2, 1, 1, 1])
    header[0].subheader(f"{game.model_key} · {game.condition} · {game.game_mode}")
    header[1].metric("Result", f"Solved in {int(game.solve_round)}" if game.solved else "Unsolved")
    header[2].metric("Score", int(game.round_score))
    header[3].metric("Secret", str(game.secret).upper())

    st.caption("Board state")
    for decision_round, row, status in states:
        label, board = st.columns([1, 4])
        label.markdown(f"**Round {decision_round}**  \n{status}")
        if status == "forfeited":
            board.markdown(wordle_row(None, None), unsafe_allow_html=True)
            board.caption(f"Rejected top-1: {str(_value(row.top1, '—')).upper()}")
        else:
            board.markdown(wordle_row(row.played_guess, row.feedback), unsafe_allow_html=True)
    if not states:
        st.info("No proposal was recorded by this round.")

    st.plotly_chart(_candidate_chart(played), width="stretch")

    st.subheader(f"Decision round {selected_round}")
    current = trajectory.loc[trajectory["decision_round"] == selected_round]
    for row in current.itertuples(index=False):
        status = "Played" if row.top1_played else ("Rejected repair" if row.proposal_type == "repair" else "Rejected")
        st.markdown(f"#### {row.proposal_type.title()} proposal · {status}")
        if row.top1_played:
            st.markdown(wordle_row(row.played_guess, row.feedback), unsafe_allow_html=True)

        ai_ig = _value(row.information_gain_top1)
        oracle = _value(row.ig_oracle)
        best_top3 = max((value for value in (_value(row.information_gain_top1),
                                             _value(row.information_gain_top2),
                                             _value(row.information_gain_top3)) if value is not None), default=None)
        cards = st.columns(5)
        cards[0].metric("AI top-1", str(_value(row.top1, "—")).upper())
        cards[1].metric("AI information gain", "—" if ai_ig is None else f"{ai_ig:.3f} bits")
        cards[2].metric("Oracle gain", "—" if oracle is None else f"{oracle:.3f} bits")
        cards[3].metric("IG efficiency", "—" if ai_ig is None or not oracle else f"{ai_ig / oracle:.1%}")
        cards[4].metric("Best AI top-3", "—" if best_top3 is None else f"{best_top3:.3f} bits")

        left, right = st.columns([3, 2])
        left.dataframe(_proposal_table(row), width="stretch", hide_index=True)
        with right:
            st.markdown("**Round diagnostics**")
            st.write(f"Candidates: **{int(row.candidate_count_before):,} → "
                     f"{int(row.candidate_count_after):,}**" if row.top1_played else
                     f"Candidates: **{int(row.candidate_count_before):,} → unchanged**")
            st.write(f"Oracle: **{row.ig_oracle_kind} action universe**")
            consistent = _value(row.top1_constraint_consistent)
            st.write(f"Constraint consistent: **{'unknown' if consistent is None else ('yes' if consistent else 'no')}**")
            ages = list(_value(row.top1_violated_constraint_ages, []))
            st.write(f"Violated clue ages: **{ages or 'none'}**")
            st.write(f"Reasoning tokens: **{int(_value(row.reasoning_tokens, 0)):,}**")
            st.write(f"Latency: **{float(_value(row.latency_ms, 0)) / 1000:.2f}s**")
            cost = _value(row.estimated_cost_usd)
            st.write(f"Estimated cost: **{'unknown' if cost is None else f'${cost:.4f}'}**")


def render(analysis_dir: Path) -> None:
    st.title("Game Explorer")
    all_games = load_table(analysis_dir, "games")
    columns = st.columns(5)
    filters = {
        "model_key": columns[0].multiselect("Model", _choices(all_games, "model_key")),
        "condition": columns[1].multiselect("Condition", _choices(all_games, "condition")),
        "game_mode": columns[2].multiselect("Mode", _choices(all_games, "game_mode")),
        "reasoning_setting": columns[3].multiselect("Reasoning", _choices(all_games, "reasoning_setting")),
        "split": columns[4].multiselect("Split", _choices(all_games, "split")),
    }
    result = st.selectbox("Result", ["All", "Solved", "Unsolved"])
    filters["solved"] = None if result == "All" else result == "Solved"
    more = st.expander("More filters")
    score = more.multiselect("Score", sorted(all_games["round_score"].dropna().unique()))
    violations, repairs = more.checkbox("Has constraint violations"), more.checkbox("Used repair")
    minimum_cost = more.number_input("Minimum cost (USD)", min_value=0.0, value=0.0)
    minimum_reasoning = more.number_input("Minimum reasoning tokens", min_value=0, value=0)
    filters["minimum_cost"] = minimum_cost if minimum_cost > 0 else None
    filters["minimum_reasoning_tokens"] = minimum_reasoning if minimum_reasoning > 0 else None
    games = filter_games(analysis_dir, filters)
    if score:
        games = games.loc[games["round_score"].isin(score)]
    if violations:
        games = games.loc[games["initial_constraint_violation_count"] > 0]
    if repairs:
        games = games.loc[games["repair_attempt_count"] > 0]
    if games.empty:
        st.info("No data available for this combination")
        return

    display = [column for column in (
        "game_id", "secret", "model_key", "condition", "game_mode", "reasoning_setting",
        "solved", "round_score", "played_guess_count", "initial_constraint_violation_count",
        "repair_attempt_count", "reasoning_tokens_total", "estimated_cost_usd_total",
    ) if column in games]
    st.dataframe(games[display], width="stretch", hide_index=True, selection_mode="single-row")
    options = [f"{row.run_id} :: {row.game_id}" for row in games.itertuples()]
    selected = st.selectbox("Open game", options, format_func=lambda value: value.split(" :: ", 1)[1])
    run_id, game_id = selected.split(" :: ", 1)
    game = games.loc[(games["run_id"] == run_id) & (games["game_id"] == game_id)].iloc[0]
    _render_replay(game, load_game_proposals(analysis_dir, run_id, game_id))
