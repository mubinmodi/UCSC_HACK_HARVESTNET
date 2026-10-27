"""Checks the WCAG AA contrast of the text/background pairs in theme.css, light and dark.
Run: python3 frontend/shared/check_contrast.py   (add -v to list every pair). Exits 1 on a failure."""
import pathlib,re,sys
css=(pathlib.Path(__file__).parent/'theme.css').read_text()
def parse(block):
    return dict(re.findall(r'--hn-([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})',block))
light=parse(css.split('/* Colors, dark')[0])
dark=parse(re.search(r':root\[data-theme="dark"\] \{(.*?)\n\}',css,re.S).group(1))
dark={**light,**dark}
def lum(h):
    c=[int(h[i:i+2],16)/255 for i in (1,3,5)]
    c=[x/12.92 if x<=0.03928 else ((x+0.055)/1.055)**2.4 for x in c]
    return 0.2126*c[0]+0.7152*c[1]+0.0722*c[2]
def cr(a,b):
    la,lb=sorted([lum(a),lum(b)],reverse=True); return (la+0.05)/(lb+0.05)
pairs=[('ink','bg',4.5),('ink','surface',4.5),('ink-2','surface',4.5),('ink-2','surface-2',4.5),('ink-2','bg',4.5),('muted','bg',4.5),('muted','surface',4.5),('muted','surface-2',4.5),
('on-leaf','leaf',4.5),('on-leaf','leaf-hover',4.5),('leaf-text','bg',4.5),('leaf-text','surface',4.5),('leaf-text','surface-2',4.5),('leaf-text','leaf-tint',4.5),('leaf-tint-ink','leaf-tint',4.5),
('on-berry','berry',4.5),('berry-text','bg',4.5),('berry-text','surface',4.5),('berry-tint-ink','berry-tint',4.5),('berry-text','berry-tint',4.5),
('cold-text','bg',4.5),('cold-text','surface',4.5),('cold-text','surface-2',4.5),('cold-tint-ink','cold-tint',4.5),
('warn-ink','warn-bg',4.5),('on-deep','deep',4.5),('on-deep','deep-2',4.5),('on-deep-muted','deep',4.5),('on-deep-muted','deep-2',4.5),('marigold','deep',3),
('line-strong','bg',3),('line-strong','surface',3),('focus','bg',3),('focus','surface',3),('focus-on-dark','deep',3),('cold','bg',3),('leaf','bg',3),
('ink','leaf-tint',4.5),('muted','leaf-tint',4.5)]
bad=0
for mode,pal in (('light',light),('dark',dark)):
    for a,b,t in pairs:
        r=cr(pal[a],pal[b])
        flag='' if r>=t else '  <-- FAIL'
        if flag: bad+=1
        if flag or '-v' in sys.argv: print(mode,a,b,round(r,2),flag)
extra=[('#2a1d00','#f2c14e',4.5),('#2a1d00','#f7d27a',4.5),('#ffffff','#153a2b',4.5)]
for a,b,t in extra:
    r=cr(a,b); print('extra',a,b,round(r,2),'' if r>=t else 'FAIL')
print('fails',bad)
sys.exit(1 if bad else 0)
