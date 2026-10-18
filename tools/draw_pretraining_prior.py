"""Original conceptual Gaussian wire surface, with hidden-line removal.

Reinterprets manuscript Figure 1b; not a fitted density or empirical result.
Uses only the standard library. No filled surface is exported to the SVG.
"""
from math import exp, floor, ceil, sqrt
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
PEAKS = [(-1.32, -.62, .88, .46), (-.10, -1.03, 1.05, .41),
         (1.28, -.44, .75, .47), (-.75, .83, .72, .49), (.72, .68, 1.17, .43)]

def surface(x, y):
    return sum(a*exp(-((x-cx)**2+(y-cy)**2)/(2*s*s)) for cx,cy,a,s in PEAKS)

def point(x, y):
    z = surface(x,y)
    return 300+62*x-49*y, 118+21*x+27*y-91*z, 49*x+62*y+(2703/91)*z

# Rasterize a dense invisible surface to resolve which wire segments face the viewer.
SCALE=3
W,H=1710,810
buffer=[float('-inf')]*(W*H)

def raster(tri):
    p=[((x-15)*SCALE,(y+35)*SCALE,d) for x,y,d in tri]
    (ax,ay,ad),(bx,by,bd),(cx,cy,cd)=p
    den=(by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
    if abs(den)<1e-8:
        return
    x0,x1=max(0,floor(min(ax,bx,cx))),min(W-1,ceil(max(ax,bx,cx)))
    y0,y1=max(0,floor(min(ay,by,cy))),min(H-1,ceil(max(ay,by,cy)))
    for iy in range(y0,y1+1):
        for ix in range(x0,x1+1):
            xx,yy=ix+.5,iy+.5
            a=((by-cy)*(xx-cx)+(cx-bx)*(yy-cy))/den
            b=((cy-ay)*(xx-cx)+(ax-cx)*(yy-cy))/den
            c=1-a-b
            if min(a,b,c)<-1e-8:
                continue
            depth=a*ad+b*bd+c*cd
            k=iy*W+ix
            if depth>buffer[k]:
                buffer[k]=depth

N=150
vertices=[[point(-2.45+4.9*i/N,-2.05+4.1*j/N) for i in range(N+1)] for j in range(N+1)]
for j in range(N):
    for i in range(N):
        a,b,c,d=vertices[j][i],vertices[j][i+1],vertices[j+1][i+1],vertices[j+1][i]
        raster((a,b,c))
        raster((a,c,d))

def visible(p):
    x,y,d=p
    ix,iy=int((x-15)*SCALE),int((y+35)*SCALE)
    return 0<=ix<W and 0<=iy<H and d>=buffer[iy*W+ix]-1.15

def tone(x,y):
    z=surface(x,y)
    e=.003
    dx=(surface(x+e,y)-surface(x-e,y))/(2*e)
    dy=(surface(x,y+e)-surface(x,y-e))/(2*e)
    light=max(0,(-.45*-dx + -.6*-dy + 1)/sqrt((dx*dx+dy*dy+1)*1.5625))
    return min(15,round(15*(.16+.56*min(1,z/1.2)+.28*light)))

def wire(points,opacity,width):
    segments=defaultdict(list)
    prev=None
    last_shade=None
    for x,y in points:
        p=point(x,y)
        shown=visible(p)
        if shown and prev and prev[3]:
            xx,yy,_,_=prev
            shade=tone(x,y)
            prefix='' if shade==last_shade else f'M{xx:.2f} {yy:.2f}'
            segments[shade].append(f'{prefix}L{p[0]:.2f} {p[1]:.2f}')
            last_shade=shade
        else:
            last_shade=None
        prev=(*p,shown)
    for shade,paths in sorted(segments.items()):
        t=shade/15
        color='#%02x%02x%02x'%tuple(round(a+(b-a)*t) for a,b in zip((57,66,85),(187,200,231)))
        svg.append(f'<path d="{"".join(paths)}" stroke="{color}" stroke-width="{width}" opacity="{opacity}"/>')

svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="15 -35 570 270" fill="none">',
     '<title>Shared generative prior</title>',
     '<desc>Conceptual Gaussian surface over CT and MRI scans, with hidden lines removed and brighter peaks to clarify depth. Illustrative, not a measured probability density.</desc>',
     '<g stroke-linecap="round" stroke-linejoin="round">']
for j in range(73):
    y=-2.05+4.1*j/72
    wire([(-2.45+4.9*i/650,y) for i in range(651)],'.9','.65')
for j in range(55):
    x=-2.45+4.9*j/54
    wire([(x,-2.05+4.1*i/550) for i in range(551)],'.58','.5')
svg.append('</g></svg>')
out=ROOT/'assets/img/concept/pretraining-prior.svg'
out.write_text('\n'.join(svg)+'\n')
print(out, out.stat().st_size)

# Four conceptual conditional-sampling routes share the camera of the mesh.
# Their locations are illustrative, not embeddings or measured model trajectories.
import json
# Locate the actual local summit, including overlap from neighboring Gaussians.
origin_x,origin_y=.72,.68
for step in [.04,.01,.002,.0004]:
    for _ in range(50):
        candidates=[(origin_x+dx*step,origin_y+dy*step) for dx in [-1,0,1] for dy in [-1,0,1]]
        best=max(candidates,key=lambda xy:surface(*xy))
        if best==(origin_x,origin_y):
            break
        origin_x,origin_y=best
start_x,start_y,_=point(origin_x,origin_y)
routes={}
for key,end,control1,control2 in [
    ('report',(-1.5,1.25),(.3,1.2),(-.8,1.6)),
    ('mask',(-.15,1.55),(.4,1.05),(.1,1.45)),
    ('translation',(1.95,.15),(1.05,.52),(1.55,.30)),
    ('treatment',(1.9,-.8),(1.25,.45),(1.85,-.05)),
]:
    # Interpolate in the surface's XY domain, then evaluate its actual height.
    # Never draw a free-floating Bezier in projected screen coordinates.
    assert surface(*end) < .3 * surface(origin_x,origin_y), 'Sampling destination must be a low region, not another peak'
    samples=[]
    for i in range(601):
        t=i/600
        weights=((1-t)**3,3*(1-t)**2*t,3*(1-t)*t*t,t**3)
        anchors=((origin_x,origin_y),control1,control2,end)
        xy=tuple(sum(w*a[k] for w,a in zip(weights,anchors)) for k in [0,1])
        samples.append(point(*xy))
    full='M'+' L'.join(f'{x:.2f} {y:.2f}' for x,y,_ in samples)
    states=[visible(p) for p in samples]
    # Suppress isolated visibility flicker along the depth-buffer silhouette.
    states=[sum(states[max(0,i-2):i+3])>=len(states[max(0,i-2):i+3])/2 for i in range(len(states))]
    trail=[]
    last_shown=False
    distances=[0]
    for i,((x,y,_),shown) in enumerate(zip(samples,states)):
        if shown:
            trail.append(f'{"L" if last_shown else "M"}{x:.2f} {y:.2f}')
        last_shown=shown
        if i:
            px,py,_=samples[i-1]
            distances.append(distances[-1]+sqrt((x-px)**2+(y-py)**2))
    times=[0.0]
    values=[int(states[0])]
    for i in range(1,len(states)-1):
        if states[i]!=states[i-1]:
            times.append(distances[i]/distances[-1])
            values.append(int(states[i]))
    times.append(1.0)
    values.append(int(states[-1]))
    x,y,_=samples[-1]
    routes[key]={'path':full,'trail':''.join(trail),'x':round(x,2),'y':round(y,2),
                 'startX':round(start_x,2),'startY':round(start_y,2),
                 'visibilityTimes':';'.join(f'{t:.6f}' for t in times),
                 'visibilityValues':';'.join(str(v) for v in values)}
route_file=ROOT/'assets/js/prior-routes.js'
route_file.write_text('// Generated by tools/draw_pretraining_prior.py. Conceptual trajectories, not model measurements.\nexport const SAMPLING_ROUTES = '+json.dumps(routes,indent=2)+';\n')
