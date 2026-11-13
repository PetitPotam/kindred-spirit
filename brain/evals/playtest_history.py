"""The conversation before a moment, from a session log, as the brain keeps it (mind.history)."""
import json,sys
S={"1943":"20261112-1943-Playground","2304":"20261112-2304-192.168.1.73_55368","2232":"20261112-2232-192.168.1.73_63665","2008":"20261112-2008-New_World_1_"}
def history(sess, idx, n=8):
    ev=[json.loads(l) for l in open('/Users/you/.kindred-spirit/logs/sessions/%s.jsonl'%S[sess])]
    out=[]
    for e in ev[:idx]:
        if e["kind"]=="you": out.append(["user",e["text"]])
        elif e["kind"]=="guest": out.append(["user","(%s, another player here, not the player you live beside, says to you in chat:) %s"%(e.get("who") or e.get("from"),e["text"])])
        elif e["kind"]=="pip":
            txt="[%s] %s"%(e.get("mood","happy"),e["text"])
            if e.get("why"): txt+=" (you said this on your own: %s)"%e["why"]
            if out and out[-1][0]=="assistant" and not e.get("why"): out[-1][1]+=" "+e["text"]
            else: out.append(["assistant",txt])
    # merge same-role neighbours like the brain
    m=[]
    for r,c in out:
        if m and m[-1][0]==r: m[-1][1]+="\n"+c
        else: m.append([r,c])
    return m[-n:] if m[-n:][0][0]=="user" else m[-(n-1):]
if __name__=="__main__":
    for r,c in history(sys.argv[1],int(sys.argv[2]),int(sys.argv[3]) if len(sys.argv)>3 else 8): print(r,":",c[:160])
