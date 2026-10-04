from market_sources import listing_median
item={"extension_fr":"Évolution Céleste","categorie":"display","titre":"Display 36 boosters – Évolution Céleste"}
def s(t,p): return {"title":t,"price":{"value":str(p)}}
L=[s("Pokémon Display Evolution Celeste 36 boosters neuf scellé",600),s("Display Évolution Céleste scellée",640),
   s("Display evolution celeste FR",620),s("Evolution Celeste display",2000),s("Carte Evolution Celeste Pikachu",5)]
r=listing_median(item,L); assert 600<=r<=640,r; print("ok listing_median",r)
assert listing_median(item,L[:2]) is None; print("ok trop peu d'annonces")
