const LABELS = {EXACT: "correct letter and position", PRESENT: "present in another position", ABSENT: "absent"};

export function wordleBoard(trajectory, {throughRound = Infinity} = {}) {
  const root = document.createElement("div");
  root.className = "wordle-board";
  const rounds = new Map();
  for (const proposal of trajectory) {
    if (proposal.decision_round <= throughRound) {
      const items = rounds.get(proposal.decision_round) ?? [];
      items.push(proposal);
      rounds.set(proposal.decision_round, items);
    }
  }
  if (!rounds.size) {
    root.classList.add("empty-board");
    root.textContent = "No proposal trajectory is available for this game.";
    return root;
  }
  for (const [round, proposals] of rounds) {
    const played = proposals.find(d => d.top1_played);
    const state = played ? (played.proposal_type === "repair" ? "played after repair" : "played") : "forfeited";
    const row = document.createElement("div");
    row.className = `board-row ${state.replaceAll(" ", "-")}`;
    const label = document.createElement("div");
    label.className = "round-label";
    label.innerHTML = `<strong>Round ${round}</strong><span>${state}</span>`;
    const tiles = document.createElement("div");
    tiles.className = "tiles";
    const guess = (played?.played_guess ?? "").toUpperCase().padEnd(5).slice(0, 5);
    const feedback = Array.from(played?.feedback ?? []);
    [...guess].forEach((letter, index) => {
      const tile = document.createElement("span");
      const result = feedback[index] ?? "NONE";
      tile.className = `wordle-tile ${result.toLowerCase()}`;
      tile.textContent = letter;
      tile.setAttribute("aria-label", `${letter || "blank"}: ${LABELS[result] ?? state}`);
      tiles.append(tile);
    });
    row.append(label, tiles);
    root.append(row);
  }
  return root;
}
