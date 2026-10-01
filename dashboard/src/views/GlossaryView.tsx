import { Plus, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, errorText } from "@/lib/api";
import { useApp } from "@/lib/store";
import type { GlossaryTerm } from "@/lib/types";

interface Row extends GlossaryTerm {
  id: number;
}
let rowSeq = 0;
const toRows = (terms: GlossaryTerm[]): Row[] => terms.map((t) => ({ ...t, id: ++rowSeq }));
const same = (a: GlossaryTerm[], b: GlossaryTerm[]) => JSON.stringify(a.map((x) => [x.term, x.meaning])) === JSON.stringify(b.map((x) => [x.term, x.meaning]));

export function GlossaryView() {
  const version = useApp((s) => s.glossaryVersion);
  const epoch = useApp((s) => s.epoch);
  const [saved, setSaved] = useState<GlossaryTerm[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const dirty = !same(saved, rows);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  useEffect(() => {
    let alive = true;
    api
      .glossary()
      .then((terms) => {
        if (!alive) return;
        setSaved(terms);
        if (!dirtyRef.current) setRows(toRows(terms));
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [version, epoch]);

  const update = (id: number, field: "term" | "meaning", value: string) => setRows((r) => r.map((x) => (x.id === id ? { ...x, [field]: value } : x)));

  return (
    <section className="rounded-3xl bg-card shadow-card">
      <div className="flex items-center gap-3 px-6 pb-4 pt-5">
        <div>
          <h2 className="text-[0.78rem] font-semibold uppercase tracking-[0.07em] text-muted">Shorthand Glossary</h2>
          <p className="mt-1 text-sm text-ink-2">The plant's abbreviations. KB uses them to understand what workers say, and they bias speech recognition.</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {dirty ? (
            <Button variant="ghost" size="sm" onClick={() => setRows(toRows(saved))}>
              Discard changes
            </Button>
          ) : null}
          <Button
            size="sm"
            disabled={!dirty || busy}
            onClick={async () => {
              setBusy(true);
              try {
                const out = await api.putGlossary(rows.filter((r) => r.term.trim()).map(({ term, meaning }) => ({ term, meaning })));
                setSaved(out);
                setRows(toRows(out));
                toast.success("Shorthand Glossary saved");
              } catch (e) {
                toast.error("Couldn't save the glossary", { description: errorText(e) });
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Saving…" : "Save glossary"}
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-[14rem_1fr_2.5rem] gap-x-3 border-t border-line px-6 py-2.5 text-[0.75rem] font-medium uppercase tracking-[0.06em] text-muted">
        <span>Term</span>
        <span>Meaning</span>
        <span />
      </div>
      <div className="grid gap-2 px-6 pb-5">
        {rows.map((r) => (
          <div key={r.id} className="grid grid-cols-[14rem_1fr_2.5rem] items-center gap-x-3">
            <Input value={r.term} onChange={(e) => update(r.id, "term", e.target.value)} className="font-mono" aria-label="Term" />
            <Input value={r.meaning} onChange={(e) => update(r.id, "meaning", e.target.value)} aria-label="Meaning" />
            <Button variant="ghost" size="icon" aria-label={`Remove ${r.term}`} onClick={() => setRows((rs) => rs.filter((x) => x.id !== r.id))}>
              <Trash2 />
            </Button>
          </div>
        ))}
        <div>
          <Button variant="outline" size="sm" className="mt-2" onClick={() => setRows((rs) => [...rs, { id: ++rowSeq, term: "", meaning: "" }])}>
            <Plus /> Add term
          </Button>
        </div>
      </div>
    </section>
  );
}
