export function gameList(games) {
  const root = document.createElement("div");
  root.className = "game-list";
  root.value = games[0] ? `${games[0].run_id}:${games[0].game_id}` : "";
  if (!games.length) {
    root.textContent = "No games match these filters.";
    return root;
  }
  const select = game => {
    root.value = `${game.run_id}:${game.game_id}`;
    root.querySelectorAll("button").forEach(button =>
      button.classList.toggle("selected", button.dataset.key === `${game.run_id}:${game.game_id}`));
    root.dispatchEvent(new Event("input", {bubbles: true}));
  };
  for (const game of games) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.key = `${game.run_id}:${game.game_id}`;
    button.className = "game-list-row";
    button.innerHTML = `<span class="game-list-id">${game.game_id}</span>
      <span>${game.model_key} · ${game.condition}</span>
      <span>${game.game_mode} · ${game.solved ? `solved ${game.solve_round}` : "unsolved"}</span>`;
    button.addEventListener("click", () => select(game));
    root.append(button);
  }
  root.firstElementChild.classList.add("selected");
  queueMicrotask(() => root.dispatchEvent(new Event("input", {bubbles: true})));
  return root;
}
