import logging as log
import traceback
from typing import List, Set
from git import Commit
from szz.common.issue_date import filter_by_date
from szz.core.abstract_szz import AbstractSZZ, ImpactedFile


class BaseSZZ(AbstractSZZ):
    """
    Base SZZ implementation.

    J. Sliwerski, T. Zimmermann, and A. Zeller, “When do changes induce fixes?” in ACM SIGSOFT Software Engineering
    Notes, vol. 30, 2005.

    Supported **kwargs:
    * ignore_revs_file_path
    """

    def __init__(self, repo_full_name: str, repo_url: str, repos_dir: str = None):
        super().__init__(repo_full_name, repo_url, repos_dir)

    def find_bic(self, fix_commit_hash: str = None, unidiff_file_path: str = None, impacted_files: List['ImpactedFile'] = None, **kwargs) -> Set[Commit]:
        """
        Find bug introducing commits candidates.

        :param str fix_commit_hash: hash of fix commit to scan for buggy commits
        :param List[ImpactedFile] impacted_files: list of impacted files in fix commit
        :key ignore_revs_file_path (str): specify ignore revs file for git blame to ignore specific commits.
        :returns Set[Commit] a set of bug introducing commits candidates, represented by Commit object
        """

        log.info(f"find_bic() kwargs: {kwargs}")

        ignore_revs_file_path = kwargs.get('ignore_revs_file_path', None)

        # support unidiff input similar to AGSZZ
        if unidiff_file_path:
            if impacted_files is None:
                impacted_files = self.get_impacted_files(unidiff_file_path=unidiff_file_path,
                                                         file_ext_to_parse=kwargs.get('file_ext_to_parse'),
                                                         only_deleted_lines=True)
            default_rev_pointer = 'HEAD'
        else:
            self._set_working_tree_to_commit(fix_commit_hash)
            default_rev_pointer = 'HEAD^'

        bic = set()
        for imp_file in impacted_files:
            try:
                # pick a rev where the file exists (like AGSZZ)
                rev_for_file = default_rev_pointer
                if not self._path_exists_in_rev(rev_for_file, imp_file.file_path):
                    fallback_rev = self._last_rev_with_path('HEAD', imp_file.file_path)
                    if not fallback_rev:
                        fallback_rev = self._last_rev_with_path(rev_for_file, imp_file.file_path)
                    rev_for_file = fallback_rev if fallback_rev else default_rev_pointer

                blame_data = self._blame(
                    rev=rev_for_file,
                    file_path=imp_file.file_path,
                    modified_lines=imp_file.modified_lines,
                    ignore_revs_file_path=ignore_revs_file_path,
                    ignore_whitespaces=False,
                    skip_comments=False
                )
                bic.update([entry.commit for entry in blame_data])
            except:
                log.error(traceback.format_exc())

        if kwargs.get('issue_date_filter', False):
            bic = filter_by_date(bic, kwargs['issue_date'])
        else:
            log.info("Not filtering by issue date.")
        
        return bic
