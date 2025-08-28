// spond/static/spond/spond.js
(function(){
  const input = document.getElementById("spondSearch");
  const list  = document.getElementById("spondResults");
  if(!input || !list) return;

  let timer = null;

  function render(items) {
    list.innerHTML = "";
    if(!items.length){
      const li = document.createElement("li");
      li.className = "list-group-item text-muted";
      li.textContent = "No results";
      list.appendChild(li);
      return;
    }
    items.forEach(i => {
      const li = document.createElement("li");
      li.className = "list-group-item d-flex justify-content-between align-items-center";
      li.innerHTML = `
        <div>
          <div class="fw-semibold">${i.name}</div>
          <div class="text-muted">${i.email || ""}</div>
        </div>
        <button class="btn btn-primary btn-sm" data-spond-pk="${i.id}">Link</button>`;
      list.appendChild(li);
    });
  }

  async function search(q) {
    const r = await fetch(`/spond/search/?q=${encodeURIComponent(q)}`);
    if(!r.ok) { render([]); return; }
    const data = await r.json();
    render(data.results || []);
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const q = input.value.trim();
      if(q.length < 2){ render([]); return; }
      search(q);
    }, 250);
  });

  list.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-spond-pk]");
  if(!btn) return;

  // disable immediately to prevent double-clicks
  if (btn.disabled) return;
  btn.disabled = true;

  const playerId = document.getElementById("spondPlayerId")?.value;
  if(!playerId) { alert("Missing player id"); return; }

  const pk = btn.getAttribute("data-spond-pk");
  const form = new FormData();
  form.append("spond_member_pk", pk);

  const resp = await fetch(`/spond/link/${playerId}/`, {
    method: "POST",
    body: form,
    headers: {"X-CSRFToken": getCookie("csrftoken")},
    credentials: "same-origin"
  });

  if ([200,201,204].includes(resp.status)) {
    btn.textContent = "Linked";
  } else {
    const text = await resp.text();
    console.error("Link failed", resp.status, text);
    alert("Failed to link");
    btn.disabled = false;  // allow retry if server failed
  }
  });


  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
  }
})();
