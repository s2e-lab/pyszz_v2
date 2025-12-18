"""
Unified diff parser utility for parsing unidiff format and extracting file changes.
"""
import logging as log
import re
from typing import List, Dict, Tuple, Optional
from szz.core.abstract_szz import ImpactedFile, LineChangeType


class UnidiffParser:
    """
    Parser for unified diff format to extract file changes and impacted lines.
    """
    
    def __init__(self):
        # Capture path token after --- or +++ up to first whitespace
        self.file_header_pattern = re.compile(r'^---\s+(\S+)')
        self.file_header_new_pattern = re.compile(r'^\+\+\+\s+(\S+)')
        self.hunk_header_pattern = re.compile(r'^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@')
        self.old_line_pattern = re.compile(r'^-')
        self.new_line_pattern = re.compile(r'^\+')
        self.context_line_pattern = re.compile(r'^ ')
    
    def parse_unidiff(self, unidiff_content: str, file_ext_to_parse: List[str] = None, 
                     only_deleted_lines: bool = True) -> List[ImpactedFile]:
        """
        Parse unidiff content and extract impacted files with modified lines.
        
        :param str unidiff_content: The unidiff content to parse
        :param List[str] file_ext_to_parse: Parse only the given file extensions
        :param bool only_deleted_lines: Consider only deleted lines as modified
        :returns List[ImpactedFile]: List of impacted files with modified lines
        """
        impacted_files = []
        lines = unidiff_content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Look for file header (--- old_file)
            if self.file_header_pattern.match(line):
                old_file_match = self.file_header_pattern.match(line)
                if old_file_match:
                    old_file_path = old_file_match.group(1)
                    
                    # Look for new file header (+++ new_file)
                    if i + 1 < len(lines):
                        new_file_line = lines[i + 1]
                        new_file_match = self.file_header_new_pattern.match(new_file_line)
                        
                        if new_file_match:
                            new_file_path = new_file_match.group(1)
                            
                            # Parse the file changes
                            file_impacted = self._parse_file_changes(
                                lines, i + 2, old_file_path, new_file_path, 
                                file_ext_to_parse, only_deleted_lines
                            )
                            
                            if file_impacted:
                                impacted_files.extend(file_impacted)
                            
                            # Move to next file section
                            i = self._find_next_file_section(lines, i + 2)
                            continue
            
            i += 1
        
        log.info(f"Parsed unidiff: found {len(impacted_files)} impacted files")
        return impacted_files
    
    def _normalize_repo_path(self, path_str: str) -> str:
        """
        Normalize paths from unidiff headers to repository-relative paths used by git blame.

        - Strip leading dataset prefixes like 'Before-<hash>/' or 'After-<hash>/'
        - Strip leading 'a/' or 'b/' prefixes
        - If a 'src/' segment exists, trim everything before it
        """
        if not path_str:
            return path_str

        # Strip leading a/ or b/
        if path_str.startswith('a/') or path_str.startswith('b/'):
            path_str = path_str[2:]

        # Strip dataset prefixes like Before-<hash>/ or After-<hash>/
        # They commonly appear as top-level directories in our generated diffs
        if path_str.startswith('Before-') or path_str.startswith('After-'):
            first_slash = path_str.find('/')
            if first_slash != -1:
                path_str = path_str[first_slash + 1:]

        # Prefer trimming to 'src/' subtree if present, since repos typically use it as root of sources
        idx = path_str.find('src/')
        if idx != -1:
            path_str = path_str[idx:]

        return path_str

    def _parse_file_changes(self, lines: List[str], start_idx: int, old_file_path: str, 
                           new_file_path: str, file_ext_to_parse: List[str] = None,
                           only_deleted_lines: bool = True) -> List[ImpactedFile]:
        """
        Parse file changes from unidiff lines.
        
        :param List[str] lines: All unidiff lines
        :param int start_idx: Starting index for this file section
        :param str old_file_path: Path to the old file
        :param str new_file_path: Path to the new file
        :param List[str] file_ext_to_parse: File extensions to parse
        :param bool only_deleted_lines: Only consider deleted lines
        :returns List[ImpactedFile]: List of impacted files for this file
        """
        impacted_files = []
        
        # Skip newly added files (no old path)
        if not old_file_path or old_file_path == '/dev/null':
            return impacted_files
        
        # Use old file path for deleted/renamed files, new path for others, then normalize
        raw_file_path = old_file_path if old_file_path != '/dev/null' else new_file_path
        file_path = self._normalize_repo_path(raw_file_path)

        # Filter by file extension after normalization
        if file_ext_to_parse:
            parts = file_path.rsplit('.', 1)
            ext = parts[1].lower() if len(parts) == 2 else ''
            if ext not in file_ext_to_parse:
                log.info(f"Skip file: {file_path}")
                return impacted_files
        
        lines_deleted = []
        lines_added = []
        
        i = start_idx
        while i < len(lines):
            line = lines[i]
            
            # Check for next file section
            if line.startswith('---'):
                break
            
            # Parse hunk header
            hunk_match = self.hunk_header_pattern.match(line)
            if hunk_match:
                old_start = int(hunk_match.group(1))
                old_count = int(hunk_match.group(2)) if hunk_match.group(2) else 1
                new_start = int(hunk_match.group(3))
                new_count = int(hunk_match.group(4)) if hunk_match.group(4) else 1
                
                # Parse lines in this hunk
                i += 1
                old_line_num = old_start
                new_line_num = new_start
                
                while i < len(lines) and not line.startswith('---'):
                    line = lines[i]
                    
                    if self.old_line_pattern.match(line):
                        # Deleted line
                        lines_deleted.append(old_line_num)
                        old_line_num += 1
                    elif self.new_line_pattern.match(line):
                        # Added line
                        lines_added.append(new_line_num)
                        new_line_num += 1
                    elif self.context_line_pattern.match(line):
                        # Context line
                        old_line_num += 1
                        new_line_num += 1
                    elif line.startswith('@@'):
                        # Next hunk
                        break
                    
                    i += 1
                continue
            
            i += 1
        
        # Create ImpactedFile objects
        if lines_deleted:
            impacted_files.append(ImpactedFile(file_path, lines_deleted, LineChangeType.DELETE))
        
        if not only_deleted_lines and lines_added:
            impacted_files.append(ImpactedFile(file_path, lines_added, LineChangeType.ADD))
        
        return impacted_files
    
    def _find_next_file_section(self, lines: List[str], start_idx: int) -> int:
        """
        Find the next file section in the unidiff.
        
        :param List[str] lines: All unidiff lines
        :param int start_idx: Starting index to search from
        :returns int: Index of next file section or end of lines
        """
        for i in range(start_idx, len(lines)):
            if lines[i].startswith('---'):
                return i
        return len(lines)


def parse_unidiff_file(file_path: str, file_ext_to_parse: List[str] = None,
                      only_deleted_lines: bool = True) -> List[ImpactedFile]:
    """
    Parse a unidiff file and return impacted files.
    
    :param str file_path: Path to the unidiff file
    :param List[str] file_ext_to_parse: File extensions to parse
    :param bool only_deleted_lines: Only consider deleted lines
    :returns List[ImpactedFile]: List of impacted files
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    parser = UnidiffParser()
    return parser.parse_unidiff(content, file_ext_to_parse, only_deleted_lines)
