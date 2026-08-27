import networkx as nx
import matplotlib.pyplot as plt
import pprint
# Crear grafo
G = nx.Graph()

# Nodos
G.add_node("R1", tipo="router")
G.add_node("S1", tipo="switch")
G.add_node("PC1", tipo="pc")
G.add_node("PC2", tipo="pc")

# Aristas
G.add_edge("R1", "S1")
G.add_edge("S1", "PC1")
G.add_edge("S1", "PC2")

# Posiciones automáticas
pos = nx.spring_layout(G)

pos = nx.spring_layout(G, seed=42)
x,y = pos['R1']
print(f"Posición de R1: x={x}, y={y}")
print(G.nodes(data=True))
print(G.edges)
##

for i in G.nodes:
    for vecino in G.neighbors(i):
        print(i, vecino)
##


# Dibujar
nx.draw(G, pos, with_labels=True)

plt.show()