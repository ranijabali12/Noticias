#!/usr/bin/env python3
"""Resumo diário: 15 principais notícias, sem repetição, sem chave de API e sem IA.

Busca feeds RSS públicos, agrupa a mesma notícia publicada por veículos diferentes,
ordena pela quantidade de veículos que cobriram e monta um resumo extrativo neutro.
Gera docs/index.html (página independente), docs/widget.json (para o widget)
e historico.json (memória do que já foi mostrado).
Só usa a biblioteca padrão do Python.
"""
import html, json, re, unicodedata, urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

BASE = Path(__file__).parent
HIST = BASE / "historico.json"
OUT = BASE / "docs"
TZ = timezone(timedelta(hours=-3))  # Brasília (sem horário de verão)
QTD = 15
MIN_FONTES = 2      # notícia precisa ter saído em pelo menos 2 veículos
JANELA_H = 30          # considera notícias publicadas nas últimas 30 h
DIAS_HIST = 60         # quanto tempo lembrar o que já foi mostrado

# Veículos de linhas editoriais diferentes, para equilibrar a seleção.
# Se algum feed parar de funcionar, ele é ignorado; basta editar esta lista.
FEEDS = {
    "g1": "https://g1.globo.com/rss/g1/",
    "Folha": "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml",
    "UOL": "https://rss.uol.com.br/feed/noticias.xml",
    "CNN Brasil": "https://www.cnnbrasil.com.br/feed/",
    "BBC Brasil": "https://feeds.bbci.co.uk/portuguese/rss.xml",
    "DW Brasil": "https://rss.dw.com/xml/rss-br-all",
    "Agência Brasil": "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml",
    "Poder360": "https://www.poder360.com.br/feed/",
    "Gazeta do Povo": "https://www.gazetadopovo.com.br/feed/rss/ultimas-noticias.xml",
    "CartaCapital": "https://www.cartacapital.com.br/feed/",
    "Jovem Pan": "https://jovempan.com.br/feed",
    "InfoMoney": "https://www.infomoney.com.br/feed/",
}

STOP = set("""a o e as os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas
para pra com sem sob sobre entre ate apos ao aos que se sua seu suas seus ele ela eles elas isso
este esta esse essa nao sim mais menos muito ja foi sao ser ter tem vai diz dizem apos contra como
quando onde qual quais quem porque pois mas ou nem tambem ainda hoje ontem amanha anos ano dia dias
veja saiba entenda video ao-vivo vivo fotos assista apos-ser""".split())

# Palavras que indicam opinião ou sensacionalismo: frases com elas perdem prioridade no resumo
RUIDO = set("""horoscopo signo loteria mega sena quina lotofacil resultado sorteio cupom promocao desconto
onde assistir escalacao palpite receita bbb fazenda novela capitulo""".split())
OPINIAO = set("""absurdo absurda chocante polemico polemica vergonha vergonhoso escandalo escandaloso
incrivel inacreditavel bizarro bizarra lamentavel brilhante desastre desastroso humilha humilhacao
detona arrasa surreal terrivel pessimo otimo fantastico genial""".split())


def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def limpar(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def tokens(t):
    t = sem_acento(t.lower())
    out = set()
    for w in re.findall(r"[a-z0-9]+", t):
        if len(w) < 3 or w in STOP:
            continue
        if len(w) > 4 and w.endswith("s"):
            w = w[:-1]
        out.add(w)
    return out


def similar(a, b):
    """Sobreposição entre conjuntos de palavras (0 a 1)."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter < 2:
        return 0.0
    return inter / min(len(a), len(b))


def data_item(el):
    for tag in ("pubDate", "{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published",
                "{http://purl.org/dc/elements/1.1/}date"):
        v = el.findtext(tag)
        if v:
            try:
                d = parsedate_to_datetime(v.strip())
            except Exception:
                try:
                    d = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
                except Exception:
                    continue
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


def ler_feed(nome, url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (resumo-diario)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raiz = ET.fromstring(r.read())
    A = "{http://www.w3.org/2005/Atom}"
    itens = raiz.iter("item")
    lista = list(itens) or list(raiz.iter(A + "entry"))
    out = []
    for el in lista:
        titulo = limpar(el.findtext("title") or el.findtext(A + "title"))
        link = el.findtext("link") or ""
        if not link.strip():
            l = el.find(A + "link")
            link = l.get("href", "") if l is not None else ""
        bruto = el.findtext("description") or el.findtext(A + "summary") or ""
        desc = limpar(bruto)
        img = ""
        for tag in ("{http://search.yahoo.com/mrss/}content", "{http://search.yahoo.com/mrss/}thumbnail", "enclosure"):
            m = el.find(tag)
            if m is not None and m.get("url") and "image" in (m.get("type") or "image") :
                img = m.get("url"); break
        if not img:
            m = re.search(r'<img[^>]+src="([^"]+)"', bruto + (el.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or ""))
            img = m.group(1) if m else ""
        if not titulo or not link:
            continue
        out.append({"fonte": nome, "titulo": titulo, "link": link.strip(), "desc": desc, "img": img, "data": data_item(el)})
    return out


def coletar(agora):
    itens, falhas = [], []
    limite = agora - timedelta(hours=JANELA_H)
    for nome, url in FEEDS.items():
        try:
            for it in ler_feed(nome, url):
                if it["data"] is None or it["data"] >= limite:
                    itens.append(it)
        except Exception as e:
            falhas.append(f"{nome}: {e.__class__.__name__}")
    return itens, falhas


def agrupar(itens):
    grupos = []
    for it in itens:
        it["tk"] = tokens(it["titulo"])
        it["tkd"] = it["tk"] | tokens(" ".join(it["desc"].split()[:40]))
        melhor, nota = None, 0
        for g in grupos:
            s = max(similar(it["tk"], g["tk"]), 0.8 * similar(it["tkd"], g["tkd"]))
            if s > nota:
                melhor, nota = g, s
        if melhor and nota >= 0.5:
            melhor["itens"].append(it)
            melhor["tk"] |= it["tk"]
            melhor["tkd"] |= it["tkd"]
        else:
            grupos.append({"itens": [it], "tk": set(it["tk"]), "tkd": set(it["tkd"])})
    return grupos


def frases(texto):
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if 40 <= len(f.strip()) <= 320]


def resumir(g):
    itens = g["itens"]
    fontes = {i["fonte"] for i in itens}
    # palavras citadas por mais de um veículo = o fato em comum
    cont = {}
    for i in itens:
        for w in i["tkd"]:
            cont.setdefault(w, set()).add(i["fonte"])
    comuns = {w for w, f in cont.items() if len(f) >= 2} or set(cont)

    # título: o mais "central" (parecido com os demais), sem ! ou ?
    def nota_titulo(i):
        c = sum(similar(i["tk"], j["tk"]) for j in itens if j is not i)
        pen = 1 if re.search(r"[!?]", i["titulo"]) else 0
        pen += 1 if tokens(i["titulo"]) & OPINIAO else 0
        return (c - pen, -len(i["titulo"]))
    titulo = re.sub(r"\s+[|–-]\s+[^|–-]{2,30}$", "", max(itens, key=nota_titulo)["titulo"])

    cand = []
    for i in itens:
        for f in frases(i["desc"]):
            tk = tokens(f)
            if not tk:
                continue
            n = len(tk & comuns) / len(tk) ** 0.5
            n += 0.3 if re.search(r"\d", f) else 0
            n -= 1.5 if tk & OPINIAO else 0
            n -= 1.0 if re.search(r"[!?]|\"|“", f) else 0
            cand.append((n, f, tk))
    cand.sort(key=lambda x: -x[0])
    escolhidas = []
    for n, f, tk in cand:
        if similar(tk, tokens(titulo)) > 0.85 or any(similar(tk, t2) > 0.6 for _, t2 in escolhidas):
            continue
        escolhidas.append((f, tk))
        if len(escolhidas) == 2 or sum(len(x) for x, _ in escolhidas) > 260:
            break
    resumo = " ".join(f for f, _ in escolhidas)
    if not resumo:
        d = max((i["desc"] for i in itens), key=len, default="")
        resumo = d[:280].rsplit(" ", 1)[0] + "…" if len(d) > 280 else d
    return titulo, resumo, sorted(fontes)


def main():
    agora = datetime.now(TZ)
    edicao = agora.date().isoformat()
    hist = json.loads(HIST.read_text("utf-8")) if HIST.exists() else []
    corte = (agora.date() - timedelta(days=DIAS_HIST)).isoformat()
    hist = [h for h in hist if h["data"] >= corte and h["data"] != edicao]  # rodar 2x no dia refaz a edição
    links_vistos = {l for h in hist for l in h["links"]}

    itens, falhas = coletar(agora)
    itens = [i for i in itens if i["link"] not in links_vistos]   # matéria já mostrada nunca volta
    grupos = agrupar(itens)
    grupos.sort(key=lambda g: (-len({i["fonte"] for i in g["itens"]}),
                               -max((i["data"] or agora).timestamp() for i in g["itens"])))

    noticias = []
    for g in grupos:
        titulo, resumo, fontes = resumir(g)
        if len(fontes) < MIN_FONTES or tokens(titulo) & RUIDO:
            continue
        tk = g["tk"]
        anterior = max(hist, key=lambda h: similar(tk, set(h["tk"])), default=None)
        s = similar(tk, set(anterior["tk"])) if anterior else 0
        if s >= 0.85:
            continue  # mesma notícia republicada, sem fato novo
        if any(similar(tk, set(n["_tk"])) >= 0.6 for n in noticias):
            continue  # evita duas versões do mesmo assunto na mesma edição
        noticias.append({
            "titulo": titulo, "resumo": resumo, "fontes": fontes,
            "links": [{"fonte": i["fonte"], "url": i["link"]} for i in g["itens"]],
            "img": next((i["img"] for i in g["itens"] if i.get("img")), ""),
            "atualizacao": (anterior["data"] if s >= 0.45 else None),
            "_tk": sorted(tk),
        })
        if len(noticias) == QTD:
            break

    for n in noticias:
        hist.append({"data": edicao, "titulo": n["titulo"], "tk": n["_tk"], "links": [l["url"] for l in n["links"]]})
    HIST.write_text(json.dumps(hist, ensure_ascii=False, indent=0), "utf-8")

    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(pagina(noticias, agora, len(FEEDS) - len(falhas), falhas), "utf-8")
    (OUT / "widget.json").write_text(json.dumps({
        "edicao": agora.strftime("%d/%m"),
        "total": len(noticias),
        "itens": [{"t": n["titulo"], "f": len(n["fontes"]), "u": bool(n["atualizacao"])} for n in noticias],
    }, ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(noticias)} notícias, {len(itens)} matérias lidas, falhas: {falhas or 'nenhuma'}")


DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


def pagina(noticias, agora, ok, falhas):
    e = html.escape
    cards = []
    for n, item in enumerate(noticias):
        k = len(item["fontes"])
        upd = ""
        if item["atualizacao"]:
            upd = f'<span class="upd">Atualização · caso de {datetime.fromisoformat(item["atualizacao"]).strftime("%d/%m")}</span>'
        img = f'<img src="{e(item["img"])}" alt="" loading="lazy" onerror="this.remove()">' if item["img"] else ""
        fontes = sorted({l["fonte"]: l for l in item["links"]}.values(), key=lambda x: x["fonte"])
        links = "".join(f'<a href="{e(l["url"])}" target="_blank" rel="noopener">{e(l["fonte"])}</a>' for l in fontes)
        cards.append(f"""<article class="{'lead' if n == 0 else ''}">
  <div class="foto">{img}</div>
  <div class="txt">{upd}<h2><a href="{e(fontes[0]['url'])}" target="_blank" rel="noopener">{e(item["titulo"])}</a></h2>
  <p>{e(item["resumo"])}</p>
  <div class="fontes"><b>{k} veículos</b>{links}</div></div>
</article>""")
    vazio = '<p class="nota">Nenhuma notícia nova nesta edição.</p>'
    data_ext = f"{DIAS[agora.weekday()].capitalize()}, {agora.day} de {MESES[agora.month - 1]}"
    aviso = f'<p class="nota">Fora do ar hoje: {e(", ".join(f.split(":")[0] for f in falhas))}.</p>' if falhas else ""
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Notícias de {agora.strftime('%d/%m')}</title>
<style>
:root{{--bg:#F3F5F8;--card:#FFF;--ink:#14202B;--sub:#5D6E7E;--line:#DDE3E9;--sol:#F0A830;--sky:#2F6FB3;
  box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0F151B;--card:#18212A;--ink:#E7EDF3;--sub:#93A3B3;--line:#26313C;--sky:#7FB2EA}}}}
*{{box-sizing:inherit}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:46rem;margin:0 auto;padding:1.6rem 1rem 3rem}}
.top{{padding:1.4rem 1.3rem;border-radius:20px;margin-bottom:1.2rem;color:#fff;
  background:linear-gradient(135deg,#1C3B5E 0%,#2F6FB3 55%,#F0A830 130%)}}
.top small{{opacity:.85;font-size:.85rem}}
.top h1{{font:700 2.1rem/1.1 Charter,"Iowan Old Style",Georgia,serif;margin:.2rem 0 .4rem}}
.top p{{margin:0;opacity:.9;font-size:.9rem}}
article{{display:grid;grid-template-columns:1fr 6.5rem;gap:1rem;background:var(--card);border-radius:16px;padding:1rem;margin-bottom:.8rem;border:1px solid var(--line)}}
.foto{{order:2}}.foto img{{width:100%;aspect-ratio:1;object-fit:cover;border-radius:12px;display:block;background:var(--line)}}
.foto:empty{{display:none}}article:has(.foto:empty){{grid-template-columns:1fr}}
article.lead{{grid-template-columns:1fr;padding:0;overflow:hidden}}
.lead .foto{{order:0}}.lead .foto img{{aspect-ratio:16/9;border-radius:0}}.lead .txt{{padding:0 1.1rem 1.1rem}}
.lead h2{{font-size:1.55rem}}
h2{{font:650 1.12rem/1.3 Charter,"Iowan Old Style",Georgia,serif;margin:.2rem 0 .45rem}}
h2 a{{color:inherit;text-decoration:none}}h2 a:hover{{color:var(--sky)}}
.txt p{{margin:0;font-size:.95rem;color:var(--ink);opacity:.88}}
.fontes{{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.7rem;font-size:.75rem}}
.fontes b{{color:var(--sol);font-weight:700;margin-right:.2rem;align-self:center}}
.fontes a{{color:var(--sub);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:.12rem .55rem}}
.upd{{display:inline-block;font-size:.75rem;font-weight:600;color:#fff;background:var(--sky);border-radius:999px;padding:.12rem .6rem}}
a:focus-visible{{outline:2px solid var(--sol);outline-offset:2px}}
.nota{{color:var(--sub);font-size:.82rem;text-align:center}}
</style></head><body><main>
<header class="top"><small>Edição das 7:30</small><h1>{data_ext}</h1>
<p>{len(noticias)} notícias que saíram em vários veículos, lidas em {ok} fontes de linhas editoriais diferentes.</p></header>
{''.join(cards) or vazio}
{aviso}
<p class="nota">Resumos feitos só com os fatos que se repetem entre os veículos.</p>
</main></body></html>"""


if __name__ == "__main__":
    main()
