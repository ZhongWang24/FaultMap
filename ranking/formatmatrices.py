"""This method is imported by looptest

@author: St. Elmo Wilken, Simon Streicher

"""

import numpy as np
import networkx as nx
import h5py



def buildcase(dummyweight, m_graph, name):
    counter = 1
    for node in m_graph.nodes():
        if m_graph.out_degree(node) == 1:
            # TODO: Investigate the effect of different weights
            nameofscale = name + str(counter) 
            m_graph.add_edge(node, nameofscale, weight=dummyweight)
            counter += 1
    
    connection = nx.to_numpy_matrix(m_graph, weight=None).T
    gain = nx.to_numpy_matrix(m_graph, weight='weight').T
    variablelist = m_graph.nodes()
    return connection, gain, variablelist


def buildgraph(variables, gainmatrix, connections):
    m_graph = nx.DiGraph()
    # Construct the graph with connections
    for col, colvar in enumerate(variables):
        for row, rowvar in enumerate(variables):
            if (connections[row, col] != 0):
                m_graph.add_edge(colvar, rowvar, weight=gainmatrix[row, col])
    return m_graph


def rankforward(variables, gainmatrix, connections, dummyweight):
    """This method adds a unit gain node to all nodes with an out-degree
    of 1; now all of these nodes should have an out-degree of 2.
    Therefore all nodes with pointers should have 2 or more edges pointing
    away from them.

    It uses the number of dummy variables to construct these gain,
    connection and variable name matrices.
    """
    
    #TODO: Rework calls of this code to reduce redundancy
    
    m_graph = buildgraph(variables, gainmatrix, connections) 
    return buildcase(dummyweight, m_graph, 'DV_forward')


def rankbackward(variables, gainmatrix, connections, dummyweight):
    """This method adds a unit gain node to all nodes with an out-degree
    of 1; now all of these nodes should have an out-degree of 2.
    Therefore all nodes with pointers should have 2 or more edges
    pointing away from them.

    It uses the number of dummy variables to construct these gain,
    connection and variable name matrices.

    This method transposes the original no dummy variables to
    generate the reverse option.

    """

    #TODO: Rework calls of this code to reduce redundancy

    m_graph = buildgraph(variables, gainmatrix.T, connections.T)
    return buildcase(dummyweight, m_graph, 'DV_backward')


def split_tsdata(tags_tsdata, datasetname, samplerate, boxsize, boxnum):
    """Splits the tags_tsdata into arrays useful for analysing the change of
    weights over time.

    samplerate is the rate of sampling in time units
    boxsize is the size of each returned dataset in time units
    boxnum is the number of boxes that need to be analyzed

    Boxes is evenly distributed over the provided dataset.
    The boxes will overlap if boxsize*boxnum is more than the simulated time,
    and will have spaced between them if it is less.


    """
    # Import the data as a numpy array
    inputdata = np.array(h5py.File(tags_tsdata, 'r')[datasetname])
    # Get total number of samples
    samples = len(inputdata)
#    print "Number of samples: ", samples
    # Convert boxsize to number of samples
    boxsizesamples = int(round(boxsize / samplerate))
#    print "Box size in samples: ", boxsizesamples
    # Calculate starting index for each box
    boxstartindex = np.empty((1, boxnum))[0]
    boxstartindex[:] = np.NAN
    boxstartindex[0] = 0
    boxstartindex[-1] = samples - boxsizesamples
    samplesbetween = int(round(boxstartindex[-1]/(boxnum-1)))
    boxstartindex[1:-1] = [(samplesbetween * index)
                           for index in range(1, boxnum-1)]
    boxes = [inputdata[boxstartindex[i]:boxstartindex[i] + boxsizesamples]
             for i in range(0, boxnum)]
    return boxes











