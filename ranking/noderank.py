# -*- coding: utf-8 -*-
"""This module is used to rank nodes in a digraph.
It requires a connection as well as a gain matrix as inputs.

Future versions will make use of an intrinsic node importance score vector (for
example, individual loop key performance indicators) as well.

@author Simon Streicher, St. Elmo Wilken

"""
# Standard libraries
import os
import json
import logging
import csv
import networkx as nx
import numpy as np
import operator
import itertools
import matplotlib.pyplot as plt
import fnmatch

# Own libraries
import data_processing
import config_setup
import ranking

import networkgen


class NoderankData:
    """Creates a data object from file and or function definitions for use in
    weight calculation methods.

    """

    def __init__(self, mode, case):

        # Get locations from configuration file
        self.saveloc, self.casedir, _ = \
            config_setup.runsetup(mode, case)
        # Load case config file
        self.caseconfig = json.load(open(os.path.join(self.casedir, case +
                                    '_noderank' + '.json')))

        # Get scenarios
        self.scenarios = self.caseconfig['scenarios']
        # Get methods
        self.methods = self.caseconfig['methods']
        # Get data type
        self.datatype = self.caseconfig['datatype']

    def scenariodata(self, scenario):
        """Retrieves data particular to each scenario for the case being
        investigated.

        """

        print "The scenario name is: " + scenario
        settings_name = self.caseconfig[scenario]['settings']
        self.connections_used = (self.caseconfig[settings_name]
                                 ['use_connections'])

        if self.datatype == 'file':

            # Retrieve connection matrix criteria from settings
            if self.connections_used:
                # Get connection (adjacency) matrix
                connectionloc = os.path.join(self.casedir, 'connections',
                                             self.caseconfig[scenario]
                                             ['connections'])
                self.connectionmatrix, self.variablelist = \
                    data_processing.read_connectionmatrix(connectionloc)

            # Get the gain matrices directory
            self.gainloc = os.path.join(self.casedir, 'gainmatrix')

        elif self.datatype == 'function':
            # Get variables, connection matrix and gainmatrix
            network_gen = self.caseconfig[scenario]['networkgen']
            self.connectionmatrix, self.gainmatrix, \
                self.variablelist, _ = \
                eval('networkgen.' + network_gen)()

        logging.info("Number of tags: {}".format(len(self.variablelist)))


def writecsv_looprank(filename, items):
    with open(filename, 'wb') as f:
        csv.writer(f).writerows(items)


def norm_dict(dictionary):
    total = sum(dictionary.values())
    # NOTE: if this is slow in Python 2, replace .items with .iteritems
    return {key: value/total for key, value in dictionary.items()}


def calc_simple_rank(gainmatrix, variables, m):
    """Constructs the ranking dictionary using the eigenvector approach
    i.e. Ax = x where A is the local gain matrix.

    Taking the absolute of the gainmatrix and normalizing to conform to
    original LoopRank idea.

    """
    # Transpose gainmatrix so that we are looking at the backwards
    # ranking problem

    gainmatrix = gainmatrix.T

    # Length of gain matrix = number of nodes
    n = gainmatrix.shape[0]
    gainmatrix = np.asmatrix(gainmatrix, dtype=float)

    # Normalize the gainmatrix columns
    for col in range(n):
        colsum = np.sum(abs(gainmatrix[:, col]))
        if colsum == 0:
            # Option :1 do nothing
            None
            # Option 2: equally connect to all other nodes
    #        for row in range(n):
    #            gainmatrix[row, col] = (1. / n)
        else:
            gainmatrix[:, col] = (gainmatrix[:, col] / colsum)

    resetmatrix = np.ones((n, n), dtype=float)/n

    weightmatrix = (m * gainmatrix) + ((1-m) * resetmatrix)

    # Normalize the weightmatrix columns
    for col in range(n):
        weightmatrix[:, col] = (weightmatrix[:, col]
                                / np.sum(abs(weightmatrix[:, col])))

    [eigval, eigvec] = np.linalg.eig(weightmatrix)
    [eigval_gain, eigvec_gain] = np.linalg.eig(gainmatrix)
    maxeigindex = np.argmax(eigval)

    rankarray = eigvec[:, maxeigindex]

    rankarray_list = [rankelement[0, 0] for rankelement in rankarray]

    # Take absolute values of ranking values
    rankarray = abs(np.asarray(rankarray_list))

    # This is the 1-dimensional array composed of rankings (normalised)
    rankarray_norm = (1 / sum(rankarray)) * rankarray

    # Create a dictionary of the rankings with their respective nodes
    # i.e. {NODE:RANKING}
    rankingdict = dict(zip(variables, rankarray_norm))

    rankinglist = sorted(rankingdict.iteritems(), key=operator.itemgetter(1),
                         reverse=True)

    # Here is the code for doing it using networkx
    weightgraph = nx.DiGraph()
    gaingraph = nx.DiGraph()

    for col, colvar in enumerate(variables):
        for row, rowvar in enumerate(variables):
            # Create fully connected weighted graph for use with eigenvector
            # centrality analysis
            weightgraph.add_edge(rowvar, colvar,
                                 weight=weightmatrix[row, col])
            # Create sparsely connected graph based on significant edge weights
            # only for use with Katz centrality analysis
            if (gainmatrix[row, col] != 0.):
                # The node order is source, sink according to
                # the convention that columns are sources and rows are sinks
                gaingraph.add_edge(rowvar, colvar,
                                   weight=gainmatrix[row, col])

    eig_rankingdict = nx.eigenvector_centrality(weightgraph.reverse())
    eig_rankingdict_norm = norm_dict(eig_rankingdict)

    katz_rankingdict = nx.katz_centrality(gaingraph.reverse(),
                                          0.99, 1.0, 20000)

    katz_rankingdict_norm = norm_dict(katz_rankingdict)

#    nx.write_gml(gaingraph, os.path.join(saveloc, "gaingraph.gml"))
#    nx.write_gml(weightgraph, os.path.join(saveloc, "weightgraph.gml"))

    return rankingdict, rankinglist


def calc_blended_rank(forwardrank, backwardrank, variablelist,
                      alpha):
    """This method creates a blended ranking profile."""
    rankingdict = dict()
    for variable in variablelist:
        rankingdict[variable] = abs(((1 - alpha) * forwardrank[variable] +
                                     (alpha) * backwardrank[variable]))

    total = sum(rankingdict.values())
    # Normalise rankings
    for variable in variablelist:
        rankingdict[variable] = rankingdict[variable] / total

    rankinglist = sorted(rankingdict.iteritems(), key=operator.itemgetter(1),
                         reverse=True)

    return rankingdict, rankinglist


def normalise_rankinglist(rankingdict, originalvariables):
    normalised_rankingdict = dict()
    for variable in originalvariables:
        normalised_rankingdict[variable] = rankingdict[variable]

    # Normalise rankings
    total = sum(normalised_rankingdict.values())
    for variable in originalvariables:
        normalised_rankingdict[variable] = \
            normalised_rankingdict[variable] / total

    normalised_rankinglist = sorted(normalised_rankingdict.iteritems(),
                                    key=operator.itemgetter(1),
                                    reverse=True)

    return normalised_rankinglist


def calc_transient_importancediffs(rankingdicts, variablelist):
    """Creates dictionary with a vector of successive differences in importance
    scores between boxes for each variable entry.

    """
    transientdict = dict()
    basevaldict = dict()
    for variable in variablelist:
        diffvect = np.empty((1, len(rankingdicts)-1))[0]
        diffvect[:] = np.NAN
        basevaldict[variable] = rankingdicts[0][variable]
        # Get initial previous importance
        prev_importance = basevaldict[variable]
        for index, rankingdict in enumerate(rankingdicts[1:]):
            diffvect[index] = rankingdict[variable] - prev_importance
            prev_importance = rankingdict[variable]
        transientdict[variable] = diffvect

    return transientdict, basevaldict


def plot_transient_importances(variables, transientdict, basevaldict):
    """Plots the transient importance for the specified variables.
    Plots both absolute rankings over time as well as ranking differences only.

    """
    transient_val_no = len(transientdict[variables[1]])
    # Transient rankings down in rows, each variable contained in a column
    diffplot = np.zeros((transient_val_no+1, len(variables)))
    absplot = np.zeros_like(diffplot)

    for index, variable in enumerate(variables):
        diffplot[:, index][1:] = transientdict[variable]
        absplot[0, index] = basevaldict[variable]
        absplot[:, index][1:] = diffplot[:, index][1:] + basevaldict[variable]

    bins = range(transient_val_no+1)

    plt.figure(1)
    plt.plot(bins, diffplot)
    plt.title('Relative importance variations over time')

    plt.figure(2)
    plt.plot(bins, absplot)
    plt.title('Absolute importance scores over time')

    return plt.figure(1), plt.figure(2)


def create_importance_graph(variablelist, closedconnections,
                            openconnections, gainmatrix, ranks):
    """Generates a graph containing the
    connectivity and importance of the system being displayed.
    Edge Attribute: color for control connection
    Node Attribute: node importance

    """

    opengraph = nx.DiGraph()

    # Verify why these indexes are switched and correct
    for col, row in itertools.izip(openconnections.nonzero()[1],
                                   openconnections.nonzero()[0]):

        opengraph.add_edge(variablelist[col], variablelist[row],
                           weight=gainmatrix[row, col])
    openedgelist = opengraph.edges()

    closedgraph = nx.DiGraph()
    for col, row in itertools.izip(closedconnections.nonzero()[1],
                                   closedconnections.nonzero()[0]):
        newedge = (variablelist[col], variablelist[row])
        closedgraph.add_edge(*newedge, weight=gainmatrix[row, col],
                             controlloop=int(newedge not in openedgelist))

    for node in closedgraph.nodes():
        closedgraph.add_node(node, importance=ranks[node])

    return closedgraph, opengraph


def gainmatrix_preprocessing(gainmatrix):
    """Moves the mean and scales the variance of the elements in the
    gainmatrix to a specified value.

    Only operates on nonzero weights.

    INCOMPLETE

    """

    # Modify the gainmatrix to have a specific mean
    # Should only be used for development analysis - generally
    # destroys information.
    # Not sure what effect will be if data is variance scaled as well.

    # Get the mean of the samples in the gainmatrix that correspond
    # to the desired connectionmatrix.
    counter = 0
    gainsum = 0
    for col, row in itertools.izip(gainmatrix.nonzero()[0],
                                   gainmatrix.nonzero()[1]):
        gainsum += gainmatrix[col, row]
        counter += 1

    currentmean = gainsum / counter
    meanscale = 1. / currentmean

    # Write meandiff to all gainmatrix elements indicated by connectionmatrix
    modgainmatrix = np.zeros_like(gainmatrix)

    for col, row in itertools.izip(gainmatrix.nonzero()[0],
                                   gainmatrix.nonzero()[1]):
        modgainmatrix[col, row] = gainmatrix[col, row] * meanscale

    return modgainmatrix, currentmean


def calc_gainrank(gainmatrix, noderankdata, dummycreation,
                  alpha, dummyweight, m):
    """Calculates the forward and backward rankings.

    """

    forwardconnection, forwardgain, forwardvariablelist = \
        data_processing.rankforward(noderankdata.variablelist,
                                    gainmatrix, noderankdata.connectionmatrix,
                                    dummyweight, dummycreation)
    backwardconnection, backwardgain, backwardvariablelist = \
        data_processing.rankbackward(noderankdata.variablelist, gainmatrix,
                                     noderankdata.connectionmatrix,
                                     dummyweight, dummycreation)

    forwardrankingdict, forwardrankinglist = \
        calc_simple_rank(forwardgain, forwardvariablelist, m)

    backwardrankingdict, backwardrankinglist = \
        calc_simple_rank(backwardgain, backwardvariablelist, m)

    blendedrankingdict, blendedrankinglist = \
        calc_blended_rank(forwardrankingdict, backwardrankingdict,
                          noderankdata.variablelist, alpha)

    rankingdicts = [blendedrankingdict, forwardrankingdict,
                    backwardrankingdict]
    rankinglists = [blendedrankinglist, forwardrankinglist,
                    backwardrankinglist]
    connections = [noderankdata.connectionmatrix, forwardconnection,
                   backwardconnection]
    variables = [noderankdata.variablelist, forwardvariablelist,
                 backwardvariablelist]
    gains = [gainmatrix, np.array(forwardgain), np.array(backwardgain)]

    return rankingdicts, rankinglists, connections, variables, gains


def get_gainmatrices(noderankdata, countlocation, gainmatrix_filename,
                     case, scenario, method):
    """Searches in countlocation for all gainmatrices CSV files
    associated with the specific case, scenario and method at hand and
    then returns all relevant gainmatrices in a list which can be used to
    calculate the change of importances over time (transient importances).

    """
    # Store all relevant gainmatrices in a list
    # The gainmatrices should be stored in the format they
    # are normally produced by the gaincalc module, namely:
    # {case}_{scenario}_{method}_maxweight_array_box{boxindex}.csv
    # where method refers to the method used to calculate the gain
    gainmatrices = []

    boxcount = 0
    for index, file in enumerate(os.listdir(noderankdata.gainloc)):
        if fnmatch.fnmatch(file, countlocation):
            boxcount += 1

    for boxindex in range(boxcount):
        gainmatrix = data_processing.read_gainmatrix(
            os.path.join(noderankdata.gainloc,
                         gainmatrix_filename.format(case, scenario,
                                                    method,
                                                    boxindex+1)))
        gainmatrices.append(gainmatrix)

    return gainmatrices


def looprank(mode, case, dummycreation, writeoutput, m, alpha=0.5):
    """Ranks the nodes in a network based on gain matrices already generated.

    """

    noderankdata = NoderankData(mode, case)

    countfile_template = '{}_{}_{}_maxweight_array_box*.csv'
    gainmatrix_filename = '{}_{}_{}_maxweight_array_box{:03d}.csv'

    # Only to be used in rare development test cases (at this stage)
    preprocessing = False

    # Define export directories and filenames
    # Get the directory to save in
    savedir = \
        config_setup.ensure_existance(
            os.path.join(noderankdata.saveloc,
                         'noderank'), make=True)

    for scenario in noderankdata.scenarios:
        logging.info("Running scenario {}".format(scenario))
        # Update scenario-specific fields of weightcalcdata object
        noderankdata.scenariodata(scenario)

        for method in noderankdata.methods:
            # Test whether the 'originalgainmatrix_box001' CSV file
            # already exists
            originalgainmatrix_template = \
                os.path.join(savedir, '{}_{}_originalgainmatrix_box{:03d}.csv')
            testlocation = \
                originalgainmatrix_template.format(scenario, method, 1)
            # TODO: Implement method in filename down below as well

            if not os.path.exists(testlocation):
                # Continue with execution
                countlocation = countfile_template.format(case,
                                                          scenario,
                                                          method)
                gainmatrices = get_gainmatrices(noderankdata, countlocation,
                                                gainmatrix_filename, case,
                                                scenario, method)

                # Create lists to store the backward ranking list
                # for each box and associated gainmatrix ranking result
                backward_rankinglists = []
                backward_rankingdicts = []

                for index, gainmatrix in enumerate(gainmatrices):
                    if preprocessing:
                        modgainmatrix, _ = \
                            gainmatrix_preprocessing(gainmatrix)
                    else:
                        modgainmatrix = gainmatrix

                    _, dummyweight = \
                        gainmatrix_preprocessing(gainmatrix)

                    rankingdicts, rankinglists, connections, \
                        variables, gains = \
                        calc_gainrank(modgainmatrix, noderankdata,
                                      dummycreation,
                                      alpha, dummyweight, m)

                    backward_rankinglists.append(rankinglists[2])
                    backward_rankingdicts.append(rankingdicts[2])

            else:
                logging.info("The requested results are in existence")

#
#            savename = rank_template.format(index)
#            writecsv_looprank(savename, rankinglist[0])
#
#            rankingdicts.append(rankingdict[0])
#
#        transientdict, basevaldict = \
#            calc_transient_importancediffs(rankingdicts, variablelist)
#
#        # Plotting functions
#        if plotting:
#            diffplot, absplot = plot_transient_importances(variablelist,
#                                                           transientdict,
#                                                           basevaldict)
#            diffplot_filename = os.path.join(saveloc,
#                                             "{}_diffplot.pdf"
#                                             .format(scenario))
#            absplot_filename = os.path.join(saveloc,
#                                            "{}_absplot.pdf"
#                                            .format(scenario))
#            diffplot.savefig(diffplot_filename)
#            absplot.savefig(absplot_filename)
#
#        logging.info("Done with transient rankings")
#
#
#
#
#            if writeoutput:
#                # Save the modified gainmatrix
#                modgainmatrix_template = \
#                    os.path.join(savedir, '{}_modgainmatrix.csv')
#                savename = modgainmatrix_template.format(scenario)
#                writecsv_looprank(savename, modgainmatrix)
#                csvfile_template = os.path.join(savedir,
#                                                '{}_{}_importances_{}.csv')
#
#                # Save the original gainmatrix
#                savename = originalgainmatrix_template.format(scenario,
#                                                              boxindex+1)
#                writecsv_looprank(savename, noderankdata.gainmatrix)
#
#                # Export graph files with dummy variables included in
#                # forward and backward rankings if available
#                directions = ['blended', 'forward', 'backward']
#
#                if dummycreation:
#                    dummystatus = 'withdummies'
#                else:
#                    dummystatus = 'nodummies'
#
#                # TODO: Do the same for meanchange
#
#                graphfile_template = os.path.join(savedir,
#                                                  '{}_{}_graph_{}.gml')
#
#                for direction, rankinglist, rankingdict, connection, \
#                    variable, gain in zip(directions, rankinglists,
#                                          rankingdicts,
#                                          connections, variables, gains):
#                    idtuple = (scenario, direction, dummystatus)
#                    # Save the ranking list to file
#                    savename = csvfile_template.format(*idtuple)
#                    writecsv_looprank(savename, rankinglist)
#                    # Save the graphs to file
#                    graph, _ = create_importance_graph(variable, connection,
#                                                       connection, gain,
#                                                       rankingdict)
#                    graph_filename = graphfile_template.format(*idtuple)
#
#                    nx.readwrite.write_gml(graph, graph_filename)
#
#                if dummycreation:
#                    # Export forward and backward ranking graphs
#                    # without dummy variables visible
#
#                    # Forward ranking graph
#                    direction = directions[1]
#                    rankingdict = rankingdicts[1]
#                    graph, _ = \
#                        create_importance_graph(noderankdata.variablelist,
#                                                noderankdata.connectionmatrix,
#                                                noderankdata.connectionmatrix,
#                                                noderankdata.gainmatrix,
#                                                rankingdict)
#                    graph_filename = os.path.join(noderankdata.saveloc,
#                                                  'noderank',
#                                                  "{}_{}_graph_dumsup.gml"
#                                                  .format(scenario, direction))
#
#                    nx.readwrite.write_gml(graph, graph_filename)
#
#                    # Backward ranking graph
#                    direction = directions[2]
#                    rankingdict = rankingdicts[2]
#                    connectionmatrix = noderankdata.connectionmatrix.T
#                    gainmatrix = noderankdata.gainmatrix.T
#                    graph, _ = \
#                        create_importance_graph(noderankdata.variablelist,
#                                                connectionmatrix,
#                                                connectionmatrix,
#                                                gainmatrix,
#                                                rankingdict)
#                    graph_filename = os.path.join(noderankdata.saveloc,
#                                                  'noderank',
#                                                  "{}_{}_graph_dumsup.gml"
#                                                  .format(scenario, direction))
#
#                    nx.readwrite.write_gml(graph, graph_filename)
#
#                    # Calculate and export normalised ranking lists
#                    # with dummy variables exluded from results
#                    for direction, rankingdict in zip(directions[1:],
#                                                      rankingdicts[1:]):
#                        normalised_rankinglist = \
#                            normalise_rankinglist(rankingdict,
#                                                  noderankdata.variablelist)
#
#                        savename = os.path.join(noderankdata.saveloc,
#                                                'noderank',
#                                                '{}_{}_importances_dumsup.csv'
#                                                .format(scenario, direction))
#                        writecsv_looprank(savename, normalised_rankinglist)


    return None
