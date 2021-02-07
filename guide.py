"""
A module to interact with graphs of places, calculate efficient routes between
nodes of that graphs and plot that routes on city maps.
The module works treating coordinates as a tuple of (latitude, longitude)
coordinates.
"""

import random
import osmnx as ox
import networkx as nx
from staticmap import StaticMap, CircleMarker, IconMarker, Line


# Constants declaration
FIND_DST = 1000  # the maximum distance to find the nearest edge
FARTHEST_NODE = 2000  # the maximum distance to consider a node out-of-bounds


def download_graph(place):
    """
    Download a graph from osmnx of the mentioned place.

    Parameters
    ----------
    place : string
        the place where the graph is downloaded

    Returns
    ----------
    networkx multidigraph
    """

    try:
        graph = ox.graph_from_place(place, network_type='drive', simplify=True)
        ox.geo_utils.add_edge_bearings(graph)

        # For each node and its information...
        for node1, info1 in graph.nodes.items():
            # For each adjacent node and its information...
            for node2, info2 in graph.adj[node1].items():
                # Only the first edge is considerated
                edge = info2[0]
                # Remove geometry information from edges because it's not
                # needed and takes a lot of space
                if 'geometry' in edge:
                    del(edge['geometry'])
    except KeyError:
        raise TypeError("Can't download a graph from " + place + ".")

    return graph


def save_graph(graph, filename):
    """
    Save a graph at the file 'filename' in gpickle format

    Parameters
    ----------
    graph : networkx multidigraph
        the graph to be saved.
    filename : string
        the name of the file where the graph is saved.

    Returns
    -------
    None.

    """

    nx.write_gpickle(graph, (filename if filename[-8:] == '.gpickle'
                             else filename+'.gpickle'))


def load_graph(filename):
    """
    Load a graph object in Python gpickle format.

    Parameters
    ----------
    filename : string
        where the graph is saved.

    Returns
    -------
    graph : networkx multidigraph

    """

    graph = nx.read_gpickle(filename if filename[-8:] == '.gpickle'
                            else filename+'.gpickle')
    return graph


def print_graph(graph):
    """
    Show the content of the nodes and edges of the graph.
    Saves the data on "graph-info-debug.txt"

    Parameters
    ----------
    graph : networkx multidigraph
        The graph to be debugged.

    Returns
    -------
    None.

    """

    text_file = open("graph-info-debug.txt", "w")
    for node1, info1 in graph.nodes.items():
        # For each adjacent node and its information...
        for node2, info2 in graph.adj[node1].items():
            try:
                text_file.write(str(info2[0]))
            # Some caracters can't be encoded on some graphs
            except:
                text_file.write("Couldn't get values for this edge")
        text_file.write("\n")
    text_file.write("\n")

    text_file.close()


def get_directions(graph, source_location, destination_location):
    """
    Compute the shortest route from location to destiny on the graph.
    The source location and destination location have to be in the bounds of
    the graph.
    The user can proceed the route by following each section (starting
    from the initial point (src), then going to (mid), and keep going forward
    on each section until the end is reached).

    Parameters
    ----------
    graph : networkx multidigraph
        The graph where all the information is taken.
    source_location : tuple
        The (latitude, longitude) where the route starts.
    destination_location : tuple
        The (latitude, longitude) that represents the destination of the route.

    Returns
    -------
    route : list
        A list of sections of the route with information. Each element of
        the list contains a dictionary with the following elements:
            angle: desviation angle of the next section.
            current_name, next_name: current and next names of the streets
            src, mid, dst: tuples (longitude, latitude)
            length: distance between the src and mid nodes

    """

    # To ensure src_node and dst_node are not outside the graph.
    source_node, src_distance = ox.get_nearest_node(graph, source_location,
                                                    return_dist=True)
    assert src_distance < FARTHEST_NODE, "source is out of bounds"

    destiny_node, dst_distance = ox.get_nearest_node(graph,
                                                     destination_location,
                                                     return_dist=True)
    assert dst_distance < FARTHEST_NODE, "destination is out of bounds"

    path = nx.shortest_path(graph, source_node, destiny_node, weight='length')

    if len(path) > 1:
        # To optimize the route, a new graph is created from truncating
        # the original with a radius from the 'source_node' to find the
        # nearest edge from source_location, otherwise the function would look
        # for all edges, which we don't need to.
        # The same it's made with the destination_location
        try:
            src_graph = ox.truncate_graph_dist(graph, source_node,
                                               max_distance=src_distance +
                                               FIND_DST)

            first_edge = ox.get_nearest_edge(src_graph, source_location)
            edge_data = graph.get_edge_data(first_edge[1], first_edge[2],
                                            key=0)

            # If the nearest edge is the same as the first edge on the path,
            # the first path node can be removed, otherwise the path would take
            # an innecessary turn.
            if (edge_data['osmid'] == graph.get_edge_data(path[0], path[1],
                                                          key=0)['osmid']):
                path.pop(0)

        except:
            print("Warning: FIND_DST is not large enough to find a edge near",
                  "the source_location. Route may not be optimized.")

        # Similar is done with the last path node
        try:
            dst_graph = ox.truncate_graph_dist(graph, destiny_node,
                                               max_distance=dst_distance +
                                               FIND_DST)

            last_edge = ox.get_nearest_edge(dst_graph, destination_location)
            edge_data = graph.get_edge_data(last_edge[1], last_edge[2], key=0)

            if (edge_data['osmid'] == graph.get_edge_data(path[-2], path[-1],
                                                          key=0)['osmid']):
                path.pop(-1)

        except:
            print("Warning: FIND_DST is not large enough to find a edge near",
                  "the destination_location. Route may not be optimized.")

    # Insertion of 'source_location' and 'destination_location' on the path.
    # 'end' is an imaginary next node which won't exist in the graph.
    path.insert(0, 'src_node')
    path.extend(('dst_node', 'end'))

    # Insertion of 'source_location' and 'destination_location' as new nodes on
    # the graph
    graph.add_node('src_node', y=source_location[0], x=source_location[1])
    graph.add_node('dst_node', y=destination_location[0],
                   x=destination_location[1])
    graph.add_node('end')

    # Last edge bearing calculation
    origin = tuple(graph.nodes[path[-3]][coord] for coord in ('x', 'y'))
    final = destination_location[::-1]

    # To ensure the polar bearing is calculated correctly
    last_bear = (ox.get_bearing(origin, final)
                 if origin <= final else ox.get_bearing(final, origin))

    # Connections of new nodes on the graph
    graph.add_edges_from([
        (path[0], path[1]),
        (path[-2], path[-1])
        ])
    graph.add_edge(path[-3], path[-2], bearing=last_bear)

    # Iteration over 'path' nodes to write 'route' information
    route = []
    mid, dst = path[0], path[1]
    for node in path[2:]:
        src, mid, dst = mid, dst, node
        # 'sm_edge' and 'md_edge' represent src-mid and mid-dst respectively
        sm_edge = graph.get_edge_data(src, mid, key=0)
        md_edge = graph.get_edge_data(mid, dst, key=0)

        try:
            angle = (md_edge['bearing'] - sm_edge['bearing']) % 360
        except:
            angle = None

        current_name = sm_edge.get('name')
        # Some edges have more than one street name
        if type(current_name) == list:
            current_name = current_name[0]

        length = sm_edge.get('length')

        next_name = md_edge.get('name')
        if type(next_name) == list:
            next_name = next_name[0]

        route.append({
            'angle': angle,
            'current_name': current_name,
            # To distinguix the imaginary node 'end' which has no coordinates.
            'dst': (tuple(graph.nodes[dst][unit] for unit in ('x', 'y'))
                    if graph.nodes[dst] else None),
            'length': length,
            'mid': tuple(graph.nodes[mid][unit] for unit in ('x', 'y')),
            'next_name': next_name,
            'src': tuple(graph.nodes[src][unit] for unit in ('x', 'y'))
                })

    # Removal of previous added nodes and edges on the graph
    graph.remove_nodes_from(('src_node', 'dst_node', 'end'))
    graph.remove_edges_from([
        (path[0], path[1]),
        (path[-3], path[-2]),
        (path[-2], path[-1])
        ])

    return route


def plot_directions(graph, source_location, destination_location, directions,
                    filename, width=400, height=400):
    """
    The main function is to plot the directions from source to destination
    on a map.
    Plot only source_location and destination_location if directions is not
    specified.
    Plot only source_location if destination_location is not specified.

    Parameters
    ----------
    graph : networkx multidigraph
    source_location : tuple
        The (latitude, longitude) source of the directions.
    destination_location : tuple
        The (latitude, longitude) destiny of the directions.
    directions : list
        A list of dicts that represents sections of the directions.
        The attributes 'src' and 'mid' must be tuples of (longitude, latitude)
        and have to be on each element of the list.
    filename : string
        The plot where the png file will be saved.
    width : int, optional
        The width resolution of the file. The function is optimized to work
        best with the default value. The default is 400.
    height : int, optional
        The height resolution of the file. The function is optimized to work
        best with the default value. The default is 400.

    Returns
    -------
    filename : string
        Where the image of the plot is saved.

    """

    mapa = StaticMap(width, height)

    if directions:
        # Print the first node (source_location)
        mapa.add_marker(IconMarker(directions[0]['src'], 'icon-location.png',
                                   40, 40))

        # Print all the nodes and edges
        for street in directions[:-1]:
            mapa.add_marker(CircleMarker(street['mid'], '#d12b2b', 9))
            edge = [street['src'], street['mid']]
            mapa.add_line(Line(edge, '#ff3333', 4))

        # Print the last node and edge (destination_location)
        mapa.add_marker(IconMarker(directions[-1]['mid'], 'icon-flag.png',
                                   40, 40))
        edge = [directions[-1]['src'], directions[-1]['mid']]
        mapa.add_line(Line(edge, '#ff3333', 4))

    else:
        if destination_location:

            # Print source_location
            mapa.add_marker(IconMarker(source_location[::-1],
                                       'icon-location.png', 40, 40))

            # Print destination_location
            mapa.add_marker(IconMarker(destination_location[::-1],
                                       'icon-flag.png', 40, 40))

        else:
            # Print source_location
            mapa.add_marker(IconMarker(source_location[::-1],
                                       'icon-location.png', 40, 40))

    # Render of the map
    imatge = mapa.render()
    # The user may have not passed the .png extension on the filename
    imatge.save(filename if filename[-4:] == '.png' else filename+'.png')

    return filename
