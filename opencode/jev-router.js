// OpenCode plugin for jev-router. Installed by install.py, which fills in the two paths below.
import { spawnSync } from "node:child_process";

const PYTHON = "__PYTHON__";
const ROUTER = "__ROUTER__";

function run(event, data) {
  const r = spawnSync(PYTHON, [ROUTER, event], { input: JSON.stringify(data), encoding: "utf8", timeout: 15000 });
  try { return JSON.parse(r.stdout || "{}"); } catch { return {}; }
}

export const JevRouter = async ({ client, directory }) => {
  const notes = new Map();
  const dirs = new Map();
  // The plugin's `directory` is where OpenCode loaded it, not always the session's folder.
  const dirOf = async (id) => {
    if (!dirs.has(id)) {
      try { dirs.set(id, (await client.session.get({ path: { id } }))?.data?.directory || directory); }
      catch { dirs.set(id, directory); }
    }
    return dirs.get(id);
  };
  const roles = new Map();
  const replies = new Map();
  return {
    "chat.message": async (input, output) => {
      const prompt = output.parts.filter((p) => p.type === "text" && !p.synthetic).map((p) => p.text).join("\n").replace(/^"([\s\S]*)"$/, "$1");
      if (!prompt) return;
      const m = output.message.model;
      const res = run("prompt", { session_id: input.sessionID, prompt, cwd: await dirOf(input.sessionID), harness: "opencode",
                                  model: m ? `${m.providerID}/${m.modelID}` : undefined });
      const note = res.hookSpecificOutput?.additionalContext || (res.decision === "block" ? `Tell the user only this: ${res.reason}` : "");
      if (note) notes.set(input.sessionID, note); else notes.delete(input.sessionID);
      if (res.jevModel) {
        const [providerID, ...rest] = res.jevModel.split("/");
        output.message.model = { providerID, modelID: rest.join("/") };
      }
    },
    "experimental.chat.system.transform": async (input, output) => {
      const note = input.sessionID && notes.get(input.sessionID);
      if (note) output.system.push(note);
    },
    event: async ({ event }) => {
      const p = event?.properties ?? {};
      if (event?.type === "message.updated" && p.info) roles.set(p.info.id, p.info.role);
      if (event?.type === "message.part.updated" && p.part?.type === "text" && roles.get(p.part.messageID) === "assistant") {
        replies.set(p.part.sessionID, p.part.text);
      }
      if (event?.type === "session.idle" && replies.has(p.sessionID)) {
        run("stop", { session_id: p.sessionID, cwd: await dirOf(p.sessionID), harness: "opencode",
                      last_assistant_message: replies.get(p.sessionID) });
        replies.delete(p.sessionID);
      }
    },
  };
};
