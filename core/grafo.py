import networkx as nx
from core.devices import(
    Device_pc as D_pc,
    Device_switch as D_sw,
    Device_router as D_r
)
from collections import defaultdict, deque
import pprint
class Grafo_red:
    def __init__(self):
        self.grafo = nx.Graph()
        self.grafo_lleno = False

    ## METODOS BASICOS ##
    def add_one_node(self, new_node):
        nombre, objecto = new_node
        self.grafo.add_node(nombre, data=objecto)

    def add_all_nodes(self, devices):
        if devices:
            for node in devices:
                nombre, objecto = node
                self.grafo.add_node(nombre, data=objecto, type=objecto.tipo)
            if not self.grafo_lleno:
                self.grafo_lleno = True
    def add_one_edge(self, one_edge):
        edge, info = one_edge
        dic= {
                edge[0]: info[0],
                edge[1]: info[2]
            }
        self.grafo.add_edge(edge[0], edge[1], data =dic)
    def add_all_edges(self, all_edges):
        for edge, info in all_edges:
            dic= {
                edge[0]: info[0],
                edge[1]: info[2]
            }
            self.grafo.add_edge(edge[0], edge[1], data =dic)
    
    def graficar(self):
        import matplotlib.pyplot as plt
        pos = nx.spring_layout(self.grafo)
        nx.draw(self.grafo, pos, with_labels=True)
        plt.show()

    ## METODOS ESPECIALES ##
    def asignar_posiciones(self, seed: int|None = 42):
        escala = len(self.grafo.nodes)*40

        for u, v, attrs in self.grafo.edges(data=True):
            tipo_u = self.grafo.nodes[u].get("type")
            tipo_v = self.grafo.nodes[v].get("type")

            attrs["weight"] = self._peso_por_tipo_arista(tipo_u, tipo_v)

        pos = nx.spring_layout(
            self.grafo,
            seed=seed,
            weight="weight",
            k=1.4,
            iterations=400
        )
        pos = {
            n: (x * escala, y * escala)
            for n, (x, y) in pos.items()
        }
        self.pos = pos
        min_x = min(x for x, y in pos.values())
        min_y = min(y for x, y in pos.values())
        dx = -min_x if min_x < 0 else 0
        dy = -min_y if min_y < 0 else 0

        for vertice in self.grafo.nodes(data=True):
            x, y = pos[vertice[0]]
            objeto: D_pc | D_sw | D_r = vertice[1]['data']
            objeto.x = round(float(x + dx) + 80, 2)
            objeto.y = round(float(y + dy) + 80, 2)
    
    def _peso_por_tipo_arista(self, tipo_u: str, tipo_v: str) -> float:
        if tipo_u == "r" and tipo_v == "r":
            return 0.5

        if (tipo_u == "r" and tipo_v == "sw") or (tipo_u == "sw" and tipo_v == "r"):
            return 1.0

        if (tipo_u == "sw" and tipo_v == "pc") or (tipo_u == "pc" and tipo_v == "sw"):
            return 0.6

        # Casos no contemplados directamente
        if tipo_u == "sw" and tipo_v == "sw":
            return 0.8

        if tipo_u == "pc" and tipo_v == "pc":
            return 0.8

        return 0.8
                
                
                


    
