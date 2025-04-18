# tree.py

from collections import defaultdict
from typing import Union
from .loaders import load_orthoxml_file, parse_orthoxml, filter_by_score
from .exceptions import OrthoXMLParsingError
from lxml import etree
from .models import Gene, Species, OrthologGroup, ParalogGroup, Taxon
from .exporters import get_ortho_pairs_recursive, get_paralog_pairs_recursive, get_ortho_pairs_iterative, get_maximal_og, compute_gene_counts_per_level, OrthoxmlToNewick

class OrthoXMLTree:
    def __init__(
        self,
        genes: dict[str, Gene],
        species: list[Species],
        groups: list[Union[OrthologGroup, ParalogGroup, Gene]],
        taxonomy: Taxon,
        xml_tree: etree.ElementTree,
        orthoxml_version: str = None
    ):
        self.genes = genes
        self.species = species
        self.groups = groups
        self.taxonomy = taxonomy
        self.xml_tree = xml_tree
        self.orthoxml_version = orthoxml_version

    def debug_repr(self) -> str:
        return f"OrthoXMLTree(genes={self.genes}, species={self.species}, groups={self.groups}, taxonomy={self.taxonomy}, orthoxml_version={self.orthoxml_version})"
        
    def __repr__(self) -> str:
        return f"OrthoXMLTree(genes=[{len(self.genes)} genes], species=[{len(self.species)} species], groups=[{len(self.groups)} groups], taxonomy=[{len(self.taxonomy)} taxons], orthoxml_version={self.orthoxml_version})"
    
    def base_stats(self) -> dict:
        """
        Compute statistics about the OrthoXML tree.

        Returns:
            dict: Statistics about the OrthoXML tree
        """
    
        return {
            "genes": len(self.genes),
            "species": len(self.species),
            "groups": len(self.groups),
            "taxonomy": len(self.taxonomy),
            "orthoxml_version": self.orthoxml_version
        }
    
    def gene_stats(self, filepath=None, sep=",") -> dict:
        """
        Compute the number of genes per taxonId level in the OrthoXML tree.
        Write to file if specified.

        Args:
            filepath: Path to write the gene stats to
            sep: Separator to use when writing to file
        Returns:
            dict: number of genes per taxonId level in the OrthoXML tree
        """
        gene_counts_per_level = compute_gene_counts_per_level(self.taxonomy, self.species)

        if filepath:
            with open(filepath, "w") as f:
                f.write(f"taxonId{sep}gene_count\n")
                for level, count in gene_counts_per_level.items():
                    f.write(f"{level}{sep}{count}\n")
        
        return gene_counts_per_level

    @classmethod
    def from_file(
        cls, 
        filepath: str,
        CompletenessScore_threshold: float = None, 
        validate: bool = False,
    ) -> "OrthoXMLTree":
        """
        Create an OrthoXMLTree instance from an OrthoXML file.

        Args:
            filepath: Path to the OrthoXML file
            CompletenessScore_threshold: Threshold value to filter by
            validate: Validate the XML file against the schema (default: False)

        Returns:
            OrthoXMLTree: Initialized OrthoXMLTree instance

        Raises:
            OrthoXMLParsingError: If there's an error loading or parsing the file
        """
        try:
            # Load XML document and validate against schema
            xml_tree = load_orthoxml_file(filepath, validate)
            
            # Apply the filter if specified
            # TODO: Refactor this to be able to filter after the loading too
            # TODO: Better abstraction for the name of the arg CompletenessScore_threshold
            if CompletenessScore_threshold:
                filter_by_score(xml_tree, "CompletenessScore", CompletenessScore_threshold)

            # Parse XML elements into domain models
            species_list, taxonomy, groups, orthoxml_version = parse_orthoxml(xml_tree)

            # TODO: Parse genes one time and avoid duplicate representations
            genes = defaultdict(Gene)
            for species in species_list:
                for gene in species.genes:
                    genes[gene._id] = gene

            # TODO: handle no taxonomy
            if not taxonomy:
                taxonomy = Taxon(id='0', name='root')
            
            return cls(
                genes=genes,
                species=species_list,
                groups=groups,
                taxonomy=taxonomy,
                xml_tree=xml_tree,
                orthoxml_version=orthoxml_version
            )

        except etree.XMLSyntaxError as e:
            raise OrthoXMLParsingError(f"Invalid XML syntax: {str(e)}") from e
        except Exception as e:
            raise OrthoXMLParsingError(f"Error parsing OrthoXML: {str(e)}") from e

    @classmethod
    def from_string(cls,
                    xml_str: str,
                    CompletenessScore_threshold: float = None
                    ) -> "OrthoXMLTree":
        """
        Create an OrthoXMLTree instance from an OrthoXML string.

        Args:
            xml_str: OrthoXML string
            CompletenessScore_threshold: Threshold value to filter by

        Returns:
            OrthoXMLTree: Initialized OrthoXMLTree instance

        Raises:
            OrthoXMLParsingError: If there's an error parsing the string
        """
        try:
            xml_tree = etree.fromstring(xml_str)

            if CompletenessScore_threshold:
                filter_by_score(xml_tree, "CompletenessScore", CompletenessScore_threshold)

            species_list, taxonomy, groups, orthoxml_version = parse_orthoxml(xml_tree)

            genes = defaultdict(Gene)
            for species in species_list:
                for gene in species.genes:
                    genes[gene._id] = gene
            
            return cls(
                genes=genes,
                species=species_list,
                groups=groups,
                taxonomy=taxonomy,
                xml_tree=xml_tree,
                orthoxml_version=orthoxml_version
            )
        except etree.XMLSyntaxError as e:
            raise OrthoXMLParsingError(f"Invalid XML syntax: {str(e)}") from e
        except Exception as e:
            raise OrthoXMLParsingError(f"Error parsing OrthoXML: {str(e)}") from e

    def split_by_rootHOGs(self) -> list["OrthoXMLTree"]:
        """
        Split the current OrthoXMLTree into multiple trees based on the root HOGs.

        Returns:
            list[OrthoXMLTree]: List of OrthoXMLTree instances created from the root HOGs.
        """
        # Identify root HOGs: OrthologGroups with no parent.
        root_hogs = [g for g in self.groups if isinstance(g, OrthologGroup)]

        ## TODO: update the genes and species and taxonomy to reflect the new tree
        trees = []
        for hog in root_hogs:
            trees.append(OrthoXMLTree(
                genes=self.genes,
                species=self.species,
                groups=hog,
                taxonomy=self.taxonomy,
                xml_tree=self.xml_tree,
                orthoxml_version=self.orthoxml_version
            ))
        return trees

    def to_orthoxml(self, filepath=None, pretty=True, use_source_tree=True) -> str:
        """
        Serialize the OrthoXMLTree to an OrthoXML file.

        Args:
            filepath: Path to write the OrthoXML file
            pretty: Pretty-print the XML output (default: True)
            use_source_tree: Use the source XML tree to generate the output (default: False)

        Returns:
            str: OrthoXML file content
        """
        if use_source_tree:
            xml_tree = self.xml_tree
        else:
            raise NotImplementedError("Generating OrthoXML from scratch is not yet supported. Please use with use_source_tree=True.")
        
        if filepath:
            with open(filepath, "wb") as f:
                f.write(etree.tostring(xml_tree, pretty_print=pretty))
        else:
            return etree.tostring(xml_tree, pretty_print=pretty).decode()

    def to_ortho_pairs(self, filepath=None, sep=",") -> list[(str, str)]:
        """
        Recursively traverse the tree and return all of the
        ortholog pairs in the tree.
        Specify a filepath if you want to write the pairs to file.

        Args:
            filepath: Path to write the pairs to
        Returns:
            list[(str, str)]: List of ortholog pairs
        """
        pairs = []
        for ortho in self.groups:
            if isinstance(ortho, OrthologGroup):
                _, valid_pairs = get_ortho_pairs_recursive(ortho)
                pairs.extend(valid_pairs)
        
        if filepath:
            with open(filepath, "w") as f:
                f.writelines(f"{a}{sep}{b}\n" for a, b in pairs)

        return pairs
    
    def to_ortho_pairs_iter(self, filepath=None, sep=","):
        """
        Generator-based method that traverses all groups in self.groups (assuming they come
        from a tree of gene groups) and yields valid ortholog pairs.
        
        If a filepath is provided, the pairs are written to the file as they are generated.
        Otherwise, a generator is returned.
        
        Args:
        filepath (str): Optional file path to which the pairs should be written.
        sep (str): Separator used when writing pairs to a file.
        
        Returns:
        If no filepath is provided, returns a generator that yields tuples (geneRef1, geneRef2).
        """
        def pair_generator():
            for group in self.groups:
                if isinstance(group, OrthologGroup):
                    yield from get_ortho_pairs_iterative(group)
        
        if filepath:
            with open(filepath, "w") as f:
                for a, b in pair_generator():
                    f.write(f"{a}{sep}{b}\n")
            # Optionally return nothing or a status.
            return
        else:
            return pair_generator()
    
    def to_ortho_pairs_of_gene(self, gene_id: str, filepath=None, sep=",") -> list[(str, str)]:
        """
        Recursively traverse the tree and return all of the
        ortholog pairs of a specific gene in the tree.

        Args:
            gene_id: Gene ID to get ortholog pairs for
        Returns:
            list[(str, str)]: List of ortholog pairs for the gene
        """
        # TODO: Refactor this to do it efficiently
        pairs = []
        for ortho in self.groups:
            if isinstance(ortho, OrthologGroup):
                _, valid_pairs = get_ortho_pairs_recursive(ortho)
                for pair in valid_pairs:
                    if gene_id in pair:
                        pairs.append(pair)
        
        if filepath:
            with open(filepath, "w") as f:
                f.writelines(f"{a}{sep}{b}\n" for a, b in pairs)

        return pairs
    
    def to_paralog_pairs(self, filepath=None, sep=",") -> list[(str, str)]:
        """
        Recursively traverse the tree and return all of the
        paralog pairs in the tree.
        Specify a filepath if you want to write the pairs to file.

        Args:
            filepath: Path to write the pairs to
        Returns:
            list[(str, str)]: List of paralog pairs
        """
        pairs = []
        
        for grp in self.groups:
            _, valid_pairs = get_paralog_pairs_recursive(grp)
            pairs.extend(valid_pairs)

        if filepath:
            with open(filepath, "w") as f:
                f.writelines(f"{a}{sep}{b}\n" for a, b in pairs)
        
        return pairs


    def to_paralog_pairs_of_gene(self, gene_id: str, filepath=None, sep=",") -> list[(str, str)]:
        """
        Recursively traverse the tree and return all of the
        paralog pairs of a specific gene in the tree.
        Specify a filepath if you want to write the pairs to file.

        Args:
            gene_id: Gene ID to get paralog pairs for
        Returns:
            list[(str, str)]: List of paralog pairs for the gene
        """
        pairs = []
        for grp in self.groups:
            _, valid_pairs = get_paralog_pairs_recursive(grp)
            for pair in valid_pairs:
                if gene_id in pair:
                    pairs.append(pair)
        if filepath:
            with open(filepath, "w") as f:
                f.writelines(f"{a}{sep}{b}\n" for a, b in pairs)
        
        return pairs

    def to_ogs(self, filepath=None) -> list[list[str]]:
        """
        Find the maximal OGs for each rHOGs.

        Args:
            filepath: Path to write the pairs to
        Returns:
            list[list[str]: list of maximal ogs for each rHOG
        """
        species_dic = {}
        for species in self.species:
            for gene in species.genes:
                species_dic[gene._id] = species.name
        
        max_ogs = []

        for group in self.groups:
            if isinstance(group, OrthologGroup):
                max_ogs.append(get_maximal_og(group, species_dic))

        if filepath:
            for i, og in enumerate(max_ogs):
                with open(f"OG_{i}_"+filepath, "w") as f:
                    f.writelines(f"{gene}\n" for gene in og) 
        return max_ogs

    def to_gene_tree(self, xref_tag="protId", encode_levels_as_nhx=False, return_gene_to_species=False, filepath=None):
        """Convert all HOGs from an orthoxml file into newick trees using a fully loaded etree.

        This function converts all top-level orthologGroups into a dictionary of newick trees.
        Duplication nodes are labeled with the NHX tag, e.g., a paralogGroup node will be translated
        into an internal node labeled as [&&NHX:Ev=duplication].

        :param filename: the filename of the input orthoxml file.
        :param xref_tag: the attribute of the <gene> element used as the leaf label.
        :param encode_levels_as_nhx: if True, the species information will be returned in NHX format,
                                    otherwise, the TaxRange value will be used as the node label.
        :param return_gene_to_species: if True, returns a tuple with the tree dictionary and a gene-to-species mapping.
        :returns: a dict of {roothogid: tree} in NHX format, or a tuple (trees, gene_to_species) if requested.
        """
        # TODO: the gene_to_species=True will break the code here!

        target = OrthoxmlToNewick(
            xref_tag=xref_tag,
            encode_levels_as_nhx=encode_levels_as_nhx,
            return_gene_to_species=return_gene_to_species)

        # TODO: for now it uses the original xml, it should use the native data to be able to track updates

        # Recursively traverse the tree to simulate start and end events.
        def traverse(elem):
            target.start(elem.tag, elem.attrib)
            for child in elem:
                traverse(child)
            target.end(elem.tag)

        traverse(self.xml_tree.getroot())
        gene_trees = target.close()

        if filepath:
            for hog_id, tree in gene_trees.items():
                with open(f"{filepath}_{hog_id}.newick", "w") as f:
                    f.write(tree)
        
        return gene_trees
