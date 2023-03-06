# Copyright 2019-2022 ETH Zurich and the DaCe authors. All rights reserved.
"""
Functionality that allows users to "cut out" parts of an SDFG in a smart way (i.e., memory preserving) for localized
testing or optimization.
"""
from collections import deque
import copy
from typing import Deque, Dict, List, Set, Tuple, Union, Optional
from dace import data
from dace.sdfg import nodes as nd, SDFG, SDFGState, utils as sdutil, InterstateEdge
from dace.memlet import Memlet
from dace.sdfg.graph import Edge, MultiConnectorEdge
from dace.sdfg.state import StateSubgraphView, SubgraphView
from dace.transformation.passes.analysis import StateReachability
from dace.properties import make_properties, SDFGReferenceProperty, SetProperty


@make_properties
class SDFGCutout(SDFG):

    original_sdfg = SDFGReferenceProperty(desc='The original SDFG the cutout was created from.', allow_none=True)
    input_config = SetProperty(element_type=str, desc='The input configuration of the cutout.')
    output_config = SetProperty(element_type=str, desc='The output configuration of the cutout.')

    def __init__(self, original_sdfg: SDFG):
        super(SDFGCutout, self).__init__(original_sdfg.name + '_cutout', original_sdfg.constants_prop)

    @classmethod
    def singlestate_cutout(cls,
                           state: SDFGState,
                           *nodes: nd.Node,
                           make_copy: bool = True,
                           make_side_effects_global: bool = True) -> 'SDFGCutout':
        """
        Cut out a subgraph of a state from an SDFG to run separately for localized testing or optimization.
        The subgraph defined by the list of nodes will be extended to include access nodes of data containers necessary
        to run the graph separately. In addition, all transient data containers that may contain data when the cutout is
        executed are made global, as well as any transient data containers which are written to inside the cutout but
        may be read after the cutout.
        
        :param state: The SDFG state in which the subgraph resides.
        :param nodes: The nodes in the subgraph to cut out.
        :param make_copy: If True, deep-copies every SDFG element in the copy. Otherwise, original references are kept.
        :param make_side_effects_global: If True, all transient data containers which are read inside the cutout but may
                                         be written to _before_ the cutout, or any data containers which are written to
                                         inside the cutout but may be read _after_ the cutout, are made global.
        :return: The created SDFGCutout.
        """
        create_element = copy.deepcopy if make_copy else (lambda x: x)
        sdfg = state.parent
        subgraph: StateSubgraphView = StateSubgraphView(state, nodes)
        subgraph = _extend_subgraph_with_access_nodes(state, subgraph)

        # Make a new SDFG with the included constants, used symbols, and data containers.
        cutout = SDFGCutout(sdfg)
        defined_syms = subgraph.defined_symbols()
        freesyms = subgraph.free_symbols
        for sym in freesyms:
            cutout.add_symbol(sym, defined_syms[sym])

        sg_edges: List[MultiConnectorEdge[Memlet]] = subgraph.edges()
        for edge in sg_edges:
            if edge.data is None or edge.data.data is None:
                continue

            memlet = edge.data
            if memlet.data in cutout.arrays:
                continue
            new_desc = sdfg.arrays[memlet.data].clone()
            cutout.add_datadesc(memlet.data, new_desc)

        # Add a single state with the extended subgraph
        new_state = cutout.add_state(state.label, is_start_state=True)
        in_translation = dict()
        out_translation = dict()
        for e in sg_edges:
            if e.src not in in_translation:
                new_el = create_element(e.src)
                in_translation[e.src] = new_el
                out_translation[new_el] = e.src
            if e.dst not in in_translation:
                new_el = create_element(e.dst)
                in_translation[e.dst] = new_el
                out_translation[new_el] = e.dst
            new_memlet = create_element(e.data)
            in_translation[e.data] = new_memlet
            out_translation[new_memlet] = e.data
            new_state.add_edge(
                in_translation[e.src], e.src_conn, in_translation[e.dst], e.dst_conn, new_memlet
            )

        # Insert remaining isolated nodes
        for n in subgraph.nodes():
            if n not in in_translation:
                new_el = create_element(n)
                in_translation[n] = new_el
                out_translation[new_el] = n
                new_state.add_node(new_el)

        # Remove remaining dangling connectors from scope nodes and add new data containers corresponding to accesses
        # for dangling connectors on other nodes.
        for orig_node in in_translation.keys():
            new_node = in_translation[orig_node]
            if isinstance(new_node, nd.Node):
                if isinstance(orig_node, (nd.EntryNode, nd.ExitNode)):
                    used_connectors = set(e.dst_conn for e in new_state.in_edges(new_node))
                    for conn in (new_node.in_connectors.keys() - used_connectors):
                        new_node.remove_in_connector(conn)
                    used_connectors = set(e.src_conn for e in new_state.out_edges(new_node))
                    for conn in (new_node.out_connectors.keys() - used_connectors):
                        new_node.remove_out_connector(conn)
                else:
                    used_connectors = set(e.dst_conn for e in new_state.in_edges(new_node))
                    for conn in (new_node.in_connectors.keys() - used_connectors):
                        prune = True
                        for e in state.in_edges(orig_node):
                            if e.dst_conn and e.dst_conn == conn:
                                _create_alibi_access_node_for_edge(
                                    cutout, new_state, sdfg, e, None, None, new_node, conn
                                )
                                prune = False
                                break
                        if prune:
                            new_node.remove_in_connector(conn)
                    used_connectors = set(e.src_conn for e in new_state.out_edges(new_node))
                    for conn in (new_node.out_connectors.keys() - used_connectors):
                        prune = True
                        for e in state.out_edges(orig_node):
                            if e.src_conn and e.src_conn == conn:
                                _create_alibi_access_node_for_edge(
                                    cutout, new_state, sdfg, e, new_node, conn, None, None
                                )
                                prune = False
                                break
                        if prune:
                            new_node.remove_out_connector(conn)

        in_translation[state] = new_state
        out_translation[new_state] = state
        in_translation[sdfg.sdfg_id] = cutout.sdfg_id
        out_translation[cutout.sdfg_id] = sdfg.sdfg_id

        # Determine what counts as inputs / outputs to the cutout and make those data containers global / non-transient.
        if make_side_effects_global:
            in_reach, out_reach = _determine_cutout_reachability(cutout, sdfg, in_translation, out_translation)
            cutout.input_config = _cutout_determine_input_config(cutout, in_reach, in_translation, out_translation)
            cutout.output_config = _cutout_determine_output_configuration(
                cutout, out_reach, in_translation, out_translation
            )
            for d_name in cutout.input_config.union(cutout.output_config):
                cutout.arrays[d_name].transient = False

        return cutout

    @classmethod
    def multistate_cutout(cls,
                          *states: SDFGState,
                          make_side_effects_global: bool = True) -> Union['SDFGCutout', SDFG]:
        """
        Cut out a multi-state subgraph from an SDFG to run separately for localized testing or optimization.

        The subgraph defined by the list of states will be extended to include any additional states necessary to make
        the resulting cutout valid and executable, i.e, to ensure that there is a distinct start state. This is achieved
        by gradually adding more states from the cutout's predecessor frontier until a distinct, single entry state is
        obtained.

        :see: _stateset_predecessor_frontier

        :param states: The subgraph states to cut out.
        :param make_side_effects_global: If True, all transient data containers which are read inside the cutout but may
                                        be written to _before_ the cutout, or any data containers which are written to
                                        inside the cutout but may be read _after_ the cutout, are made global.
        :return: The created SDFGCutout or the original SDFG where no smaller cutout could be obtained.
        """
        create_element = copy.deepcopy

        # Check that all states are inside the same SDFG.
        sdfg = list(states)[0].parent
        if any(i.parent != sdfg for i in states):
            raise Exception('Not all cutout states reside in the same SDFG')

        cutout_states: Set[SDFGState] = set(states)

        # Determine the start state and ensure there IS a unique start state. If there is no unique start state, keep
        # adding states from the predecessor frontier in the state machine until a unique start state can be determined.
        start_state: Optional[SDFGState] = None
        for state in cutout_states:
            if state == sdfg.start_state:
                start_state = state
                break

        if start_state is None:
            bfs_queue: Deque[Tuple[Set[SDFGState], Set[Edge[InterstateEdge]]]] = deque()
            bfs_queue.append(_stateset_predecessor_frontier(cutout_states))

            while len(bfs_queue) > 0:
                frontier, frontier_edges = bfs_queue.popleft()
                if len(frontier_edges) == 0:
                    # No explicit start state, but also no frontier to select from.
                    return sdfg
                elif len(frontier_edges) == 1:
                    # If there is only one predecessor frontier edge, its destination must be the start state.
                    start_state = list(frontier_edges)[0].dst
                else:
                    if len(frontier) == 0:
                        # No explicit start state, but also no frontier to select from.
                        return sdfg
                    if len(frontier) == 1:
                        # For many frontier edges but only one frontier state, the frontier state is the new start state
                        # and is included in the cutout.
                        start_state = list(frontier)[0]
                        cutout_states.add(start_state)
                    else:
                        for s in frontier:
                            cutout_states.add(s)
                        bfs_queue.append(_stateset_predecessor_frontier(cutout_states))

        subgraph: SubgraphView = SubgraphView(sdfg, cutout_states)

        # Make a new SDFG with the included constants, used symbols, and data containers.
        cutout = SDFGCutout(sdfg)
        defined_symbols: Dict[str, data.Data] = dict()
        free_symbols: Set[str] = set()
        for state in cutout_states:
            free_symbols |= state.free_symbols
            state_defined_symbols = state.defined_symbols()
            for sym in state_defined_symbols:
                defined_symbols[sym] = state_defined_symbols[sym]
        for sym in free_symbols:
            cutout.add_symbol(sym, defined_symbols[sym])

        for state in cutout_states:
            for dnode in state.data_nodes():
                if dnode.data in cutout.arrays:
                    continue
                new_desc = sdfg.arrays[dnode.data].clone()
                cutout.add_datadesc(dnode.data, new_desc)

        # Add all states and state transitions required to the new cutout SDFG by traversing the state machine edges.
        sg_edges: List[Edge[InterstateEdge]] = subgraph.edges()
        in_translation = dict()
        out_translation = dict()
        for is_edge in sg_edges:
            if is_edge.src not in in_translation:
                new_el: SDFGState = create_element(is_edge.src)
                in_translation[is_edge.src] = new_el
                out_translation[new_el] = is_edge.src
                cutout.add_node(new_el, is_start_state=(is_edge.src == start_state))
                new_el.parent = cutout
            if is_edge.dst not in in_translation:
                new_el: SDFGState = create_element(is_edge.dst)
                in_translation[is_edge.dst] = new_el
                out_translation[new_el] = is_edge.dst
                cutout.add_node(new_el, is_start_state=(is_edge.dst == start_state))
                new_el.parent = cutout
            new_isedge: InterstateEdge = create_element(is_edge.data)
            in_translation[is_edge.data] = new_isedge
            out_translation[new_isedge] = is_edge.data
            cutout.add_edge(in_translation[is_edge.src], in_translation[is_edge.dst], new_isedge)

        # Add remaining necessary states.
        for state in subgraph.nodes():
            if state not in in_translation:
                new_el = create_element(state)
                in_translation[state] = new_el
                out_translation[new_el] = state
                cutout.add_node(new_el, is_start_state=(state == start_state))
                new_el.parent = cutout

        in_translation[sdfg.sdfg_id] = cutout.sdfg_id
        out_translation[cutout.sdfg_id] = sdfg.sdfg_id

        # Check interstate edges for missing data descriptors.
        for e in cutout.edges():
            for s in e.data.free_symbols:
                if s in sdfg.arrays and s not in cutout.arrays:
                    desc = sdfg.arrays[s]
                    cutout.add_datadesc(s, desc)

        # Determine what counts as inputs / outputs to the cutout and make those data containers global / non-transient.
        if make_side_effects_global:
            in_reach, out_reach = _determine_cutout_reachability(cutout, sdfg, in_translation, out_translation)
            cutout.input_config = _cutout_determine_input_config(cutout, in_reach, in_translation, out_translation)
            cutout.output_config = _cutout_determine_output_configuration(
                cutout, out_reach, in_translation, out_translation
            )
            for d_name in cutout.input_config.union(cutout.output_config):
                cutout.arrays[d_name].transient = False

        return cutout


def _stateset_predecessor_frontier(states: Set[SDFGState]) -> Tuple[Set[SDFGState], Set[Edge[InterstateEdge]]]:
    """
    For a set of states, return their predecessor frontier.
    The predecessor frontier refers to the predecessor states leading into any of the states in the given set.

    For example, if the given set is {C, D}, and the graph is induced by the edges
    {(A, B), (B, C), (C, D), (D, E), (B, D), (A, E), (A, C)}, then the predecessor frontier consists of the states
    {A, B} and edges {(A, C), (B, C), (B, D)}.

    :param states: The set of states to find the predecessor frontier of.
    :return: A tuple of the predecessor frontier states and the predecessor frontier edges.
    """
    pred_frontier = set()
    pred_frontier_edges = set()
    for state in states:
        for iedge in state.parent.in_edges(state):
            if iedge.src not in states:
                if iedge.src not in pred_frontier:
                    pred_frontier.add(iedge.src)
                if iedge not in pred_frontier_edges:
                    pred_frontier_edges.add(iedge)
    return pred_frontier, pred_frontier_edges


def _create_alibi_access_node_for_edge(target_sdfg: SDFG, target_state: SDFGState, original_sdfg: SDFG,
                                       original_edge: MultiConnectorEdge[Memlet], from_node: Union[nd.Node, None],
                                       from_connector: Union[str, None], to_node: Union[nd.Node, None],
                                       to_connector: Union[str, None]) -> data.Data:
    """
    Add an alibi data container and access node to a dangling connector inside of scopes.
    Alibi nodes are never transient because they always represent a 'border' of the cutout and will consequently
    be accessed by other nodes outside of the cutout (i.e. at a minimum the data containers they are extracted from).
    """
    original_edge.data
    access_size = original_edge.data.subset.size_exact()
    container_name = '__cutout_' + str(original_edge.data.data)
    container_name = data.find_new_name(container_name, target_sdfg._arrays.keys())
    original_array = original_sdfg._arrays[original_edge.data.data]
    memlet_str = ''
    if original_edge.data.subset.num_elements_exact() > 1:
        access_size = original_edge.data.subset.size_exact()
        target_sdfg.add_array(container_name, access_size, original_array.dtype)
        memlet_str = container_name + '['
        sep = None
        for dim_len in original_edge.data.subset.bounding_box_size():
            if sep is not None:
                memlet_str += ','
            if dim_len > 1:
                memlet_str += '0:' + str(dim_len - 1)
            else:
                memlet_str += '0'
            sep = ','
        memlet_str += ']'
    else:
        target_sdfg.add_scalar(container_name, original_array.dtype)
        memlet_str = container_name + '[0]'
    alibi_access_node = target_state.add_access(container_name)
    if from_node is None:
        target_state.add_edge(alibi_access_node, None, to_node, to_connector, Memlet(memlet_str))
    else:
        target_state.add_edge(from_node, from_connector, alibi_access_node, None, Memlet(memlet_str))
    return target_sdfg.arrays[container_name]


def _extend_subgraph_with_access_nodes(state: SDFGState, subgraph: StateSubgraphView) -> StateSubgraphView:
    """ Expands a subgraph view to include necessary input/output access nodes, using memlet paths. """
    sdfg = state.parent
    result: List[nd.Node] = copy.copy(subgraph.nodes())
    queue: Deque[nd.Node] = deque(subgraph.nodes())

    # Add all nodes in memlet paths
    while len(queue) > 0:
        node = queue.pop()
        if isinstance(node, nd.AccessNode):
            if isinstance(node.desc(sdfg), data.View):
                vnode = sdutil.get_view_node(state, node)
                result.append(vnode)
                queue.append(vnode)
            continue
        for e in state.in_edges(node):
            # Special case: IN_* connectors are not traversed further
            if isinstance(e.dst, (nd.EntryNode, nd.ExitNode)) and (e.dst_conn is None or e.dst_conn.startswith('IN_')):
                continue

            # We don't want to extend access nodes over scope entry nodes, but rather we want to introduce alibi data
            # containers for the correct subset instead. Handled separately in _create_alibi_access_node_for_edge.
            if isinstance(e.src, nd.EntryNode) and e.src not in result and state.exit_node(e.src) not in result:
                continue

            mpath = state.memlet_path(e)
            new_nodes = [mpe.src for mpe in mpath if mpe.src not in result]
            result.extend(new_nodes)
            # Memlet path may end in a code node, continue traversing and expanding graph
            queue.extend(new_nodes)

        for e in state.out_edges(node):
            # Special case: OUT_* connectors are not traversed further
            if isinstance(e.src, (nd.EntryNode, nd.ExitNode)) and (e.src_conn is None or e.src_conn.startswith('OUT_')):
                continue

            # We don't want to extend access nodes over scope exit nodes, but rather we want to introduce alibi data
            # containers for the correct subset instead. Handled separately in _create_alibi_access_node_for_edge.
            if isinstance(e.dst, nd.ExitNode) and e.dst not in result and state.entry_node(e.dst) not in result:
                continue

            mpath = state.memlet_path(e)
            new_nodes = [mpe.dst for mpe in mpath if mpe.dst not in result]
            result.extend(new_nodes)
            # Memlet path may end in a code node, continue traversing and expanding graph
            queue.extend(new_nodes)

    # Check for mismatch in scopes
    for node in result:
        enode = None
        if isinstance(node, nd.EntryNode) and state.exit_node(node) not in result:
            enode = state.exit_node(node)
        if isinstance(node, nd.ExitNode) and state.entry_node(node) not in result:
            enode = state.entry_node(node)
        if enode is not None:
            raise ValueError(f'Cutout cannot expand graph implicitly since "{node}" is in the graph and "{enode}" is '
                             'not. Please provide more nodes in the subgraph as necessary.')

    return StateSubgraphView(state, result)


def _determine_cutout_reachability(
        ct: SDFG,
        sdfg: SDFG,
        in_translation: dict,
        out_translation: dict,
        state_reach: Dict[SDFGState, Set[SDFGState]] = None) -> Tuple[Set[SDFGState], Set[SDFGState]]:
    """
    For a given cutout and its original SDFG, determine what parts of the SDFG (set of states) can reach the cutout,
    and what set of states can be reached from the cutout.

    :param ct: The cutout SDFG.
    :param sdfg: The original SDFG.
    :param in_translation: The translation dictionary from the original SDFG elements to cutout elements.
    :param out_translation: The translation dictionary from the cutout elements to original SDFG elements.
    :param state_reach: The state reachability dictionary for the original SDFG. If not provided, it will be computed
                        on-the-fly.
    :return: A tuple of two sets of states. The first set contains the states that can reach the cutout, and the second
             set contains the states that can be reached from the cutout.
    """
    if state_reach is None:
        original_sdfg_id = out_translation[sdfg.sdfg_id]
        state_reachability_dict = StateReachability().apply_pass(sdfg.sdfg_list[original_sdfg_id], None)
        state_reach = state_reachability_dict[original_sdfg_id]
    inverse_cutout_reach: Set[SDFGState] = set()
    cutout_reach: Set[SDFGState] = set()
    cutout_states = set(ct.states())
    for state in cutout_states:
        original_state = out_translation[state]
        for k, v in state_reach.items():
            if (k not in in_translation or in_translation[k] not in cutout_states):
                if original_state is not None and original_state in v:
                    inverse_cutout_reach.add(k)
        for rstate in state_reach[original_state]:
            if (rstate not in in_translation or in_translation[rstate] not in cutout_states):
                cutout_reach.add(rstate)
    return (inverse_cutout_reach, cutout_reach)


def _cutout_determine_input_config(ct: SDFG, inverse_cutout_reach: Set[SDFGState], in_translation: dict,
                                   out_translation: dict) -> Set[str]:
    """
    Determines the input configuration for a given cutout SDFG.
    The input configuration is the set of data descriptors that are read inside the cutout, but may be written to
    before the cutout is executed. Consequently, this contains any data container that may influence the computations
    inside the cutout.

    :param ct: The cutout SDFG.
    :param inverse_cutout_reach: The set of states that can reach the cutout.
    :param in_translation: The translation dictionary from the original SDFG elements to cutout elements.
    :param out_translation: The translation dictionary from the cutout elements to original SDFG elements.
    :return: The set of data descriptor names that are part of the input configuration.
    """
    input_configuration = set()
    check_for_write_before = set()
    cutout_states = set(ct.states())

    noded_descriptors = set()

    for state in cutout_states:
        for dn in state.data_nodes():
            noded_descriptors.add(dn.data)

            array = ct.arrays[dn.data]
            if not array.transient:
                # Non-transients are always part of the system state.
                input_configuration.add(dn.data)
            elif state.out_degree(dn) > 0:
                # This is read from, add to the system state if it is written anywhere else in the graph.
                check_for_write_before.add(dn.data)

        original_state: Optional[SDFGState] = None
        try:
            original_state = out_translation[state]
        except KeyError:
            original_state = None

        # If the cutout consists of only one state, we need to check inside the same state of the original SDFG as well.
        if len(cutout_states) == 1 and original_state is not None:
            for dn in original_state.data_nodes():
                if original_state.in_degree(dn) > 0:
                    iedges = original_state.in_edges(dn)
                    if any([i.src not in in_translation for i in iedges]):
                        if dn.data in check_for_write_before:
                            input_configuration.add(dn.data)

    for state in inverse_cutout_reach:
        for dn in state.data_nodes():
            if state.in_degree(dn) > 0:
                # For any writes, check if they are reads from the cutout that need to be checked. If they are, they're
                # part of the system state.
                if dn.data in check_for_write_before:
                    input_configuration.add(dn.data)

    # Anything that doesn't have a correpsonding access node must be used as well.
    for desc in ct.arrays.keys():
        if desc not in noded_descriptors:
            input_configuration.add(desc)

    return input_configuration


def _cutout_determine_output_configuration(ct: SDFG, cutout_reach: Set[SDFGState], in_translation: dict,
                                           out_translation: dict) -> Set[str]:
    """
    Determines the output configuration for a given cutout SDFG.
    The output configuration is the set of data descriptors that are written inside the cutout, but may be read from
    after the cutout is executed. Consequently, this contains any data container that may influence the computations
    of the original SDFG after the cutout.

    :param ct: The cutout SDFG.
    :param cutout_reach: The set of states that can be reached from the cutout.
    :param in_translation: The translation dictionary from the original SDFG elements to cutout elements.
    :param out_translation: The translation dictionary from the cutout elements to original SDFG elements.
    :return: The set of data descriptor names that are part of the output configuration.
    """
    system_state = set()
    check_for_read_after = set()
    cutout_states = set(ct.states())

    for state in cutout_states:
        for dn in state.data_nodes():
            array = ct.arrays[dn.data]
            if not array.transient:
                # Non-transients are always part of the system state.
                system_state.add(dn.data)
            elif state.in_degree(dn) > 0:
                # This is written to, add to the system state if it is read anywhere else in the graph.
                check_for_read_after.add(dn.data)

        original_state: SDFGState = out_translation[state]

        # If the cutout consists of only one state, we need to check inside the same state of the original SDFG as well.
        if len(cutout_states) == 1:
            for dn in original_state.data_nodes():
                if original_state.out_degree(dn) > 0:
                    oedges = original_state.out_edges(dn)
                    if any([o.dst not in in_translation for o in oedges]):
                        if dn.data in check_for_read_after:
                            system_state.add(dn.data)

    for state in cutout_reach:
        for dn in state.data_nodes():
            if state.out_degree(dn) > 0:
                # For any reads, check if they are writes from the cutout that need to be checked. If they are, they're
                # part of the system state.
                if dn.data in check_for_read_after:
                    system_state.add(dn.data)

    return system_state
