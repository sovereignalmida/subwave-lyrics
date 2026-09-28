const ui = {
  title: document.querySelector("#title"),
  artist: document.querySelector("#artist"),
  album: document.querySelector("#album"),
  artwork: document.querySelector("#artwork"),
  artworkPlaceholder: document.querySelector("#artwork-placeholder"),
  lyrics: document.querySelector("#lyrics"),
  connection: document.querySelector("#connection"),
  progress: document.querySelector("#progress-bar"),
};

let state = null;
let identity = null;
let renderedLyricsKey = null;
let activeIndex = -2;
let receivedAt = 0;

function trackIdentity(track) {
  return track ? `${track.subsonic_id || `${track.artist}|${track.title}`}|${track.started_at}` : null;
}

function setArtwork(track, changed) {
  if (!track?.subsonic_id) {
    ui.artwork.hidden = true;
    ui.artworkPlaceholder.hidden = false;
    return;
  }
  if (changed) {
    ui.artwork.src = `/api/artwork/current?v=${encodeURIComponent(track.started_at)}`;
  }
}

ui.artwork.addEventListener("load", () => {
  ui.artwork.hidden = false;
  ui.artworkPlaceholder.hidden = true;
});
ui.artwork.addEventListener("error", () => {
  ui.artwork.hidden = true;
  ui.artworkPlaceholder.hidden = false;
});

function renderLyrics(lyrics) {
  const key = JSON.stringify([lyrics.status, lyrics.type, lyrics.lines?.length, lyrics.plain?.length]);
  if (key === renderedLyricsKey) return;
  renderedLyricsKey = key;
  activeIndex = -2;
  ui.lyrics.replaceChildren();

  if (lyrics.type === "synced") {
    const fragment = document.createDocumentFragment();
    lyrics.lines.forEach((line, index) => {
      const element = document.createElement("p");
      element.className = "lyric-line";
      element.dataset.index = index;
      element.textContent = line.text || "♪";
      fragment.appendChild(element);
    });
    ui.lyrics.appendChild(fragment);
    return;
  }
  if (lyrics.type === "plain") {
    const element = document.createElement("div");
    element.className = "plain-lyrics";
    element.textContent = lyrics.plain;
    ui.lyrics.appendChild(element);
    return;
  }

  const empty = document.createElement("p");
  empty.className = "empty-state";
  empty.textContent = lyrics.status === "loading" ? "Finding lyrics…" : lyrics.status === "error" ? "Lyrics service unavailable" : "Lyrics unavailable";
  ui.lyrics.appendChild(empty);
}

function renderSnapshot(snapshot) {
  state = snapshot;
  receivedAt = performance.now();
  const nextIdentity = trackIdentity(snapshot.track);
  const changed = nextIdentity !== identity;
  identity = nextIdentity;

  if (!snapshot.connected) {
    ui.connection.textContent = "Station unavailable";
  } else if (!snapshot.playing) {
    ui.connection.textContent = "Off air";
  } else {
    ui.connection.textContent = snapshot.lyrics.type === "synced" ? "Synchronized lyrics" : snapshot.lyrics.type === "plain" ? "Lyrics" : "On air";
  }

  if (snapshot.track) {
    ui.title.textContent = snapshot.track.title;
    ui.artist.textContent = snapshot.track.artist;
    ui.album.textContent = [snapshot.track.album, snapshot.track.year].filter(Boolean).join(" · ");
  } else {
    ui.title.textContent = snapshot.connected ? "Nothing playing" : "Waiting for the station";
    ui.artist.textContent = "SUB/WAVE";
    ui.album.textContent = "";
  }
  setArtwork(snapshot.track, changed);
  renderLyrics(snapshot.lyrics);
}

function tick() {
  if (!state?.track || state.playback.elapsed == null) {
    ui.progress.style.width = "0%";
    return;
  }
  const elapsed = state.playback.elapsed + (performance.now() - receivedAt) / 1000;
  if (state.track.duration) {
    ui.progress.style.width = `${Math.min(100, Math.max(0, elapsed / state.track.duration * 100))}%`;
  }
  if (state.lyrics.type !== "synced") return;

  let next = -1;
  for (let index = 0; index < state.lyrics.lines.length; index += 1) {
    if (state.lyrics.lines[index].time > elapsed) break;
    next = index;
  }
  if (next === activeIndex) return;
  if (activeIndex >= 0) ui.lyrics.querySelector(`[data-index="${activeIndex}"]`)?.classList.remove("active");
  activeIndex = next;
  if (activeIndex >= 0) {
    const line = ui.lyrics.querySelector(`[data-index="${activeIndex}"]`);
    line?.classList.add("active");
    line?.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

async function refresh() {
  try {
    const response = await fetch("/api/display", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderSnapshot(await response.json());
  } catch {
    ui.connection.textContent = "Display service unavailable";
  }
}

async function heartbeat() {
  try {
    await fetch("/api/viewer-heartbeat", { method: "POST", cache: "no-store" });
  } catch {
    // The visible connection state is driven by /api/display.
  }
}

heartbeat();
refresh();
setInterval(heartbeat, 20000);
setInterval(refresh, 2000);
setInterval(tick, 250);
