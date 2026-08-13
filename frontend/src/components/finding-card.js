export function findingCard({title, result, interpretation, caveats = [], complete = true}) {
  const article = document.createElement("article");
  article.className = `finding ${complete ? "" : "provisional"}`;
  article.innerHTML = `
    <p class="eyebrow">Finding</p>
    <h3>${title}</h3>
    <div class="finding-block result"><span>Result</span><p>${result}</p></div>
    <div class="finding-block interpretation"><span>Interpretation</span><p>${complete ? interpretation : "Withheld until the referenced comparison is complete."}</p></div>
    ${caveats.map(text => `<div class="finding-block caveat"><span>Caveat</span><p>${text}</p></div>`).join("")}`;
  return article;
}
