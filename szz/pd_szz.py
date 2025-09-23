import logging as log
from typing import List, Set
from git import Commit
from pydriller import GitRepository
from szz.common.issue_date import filter_by_date
from szz.core.abstract_szz import AbstractSZZ, ImpactedFile


def match_files(file: str, impacted_files: List['ImpactedFile']) -> bool:
    for entry in impacted_files:
        if entry.file_path == file:
            return True
    return False


class PyDrillerSZZ(AbstractSZZ):
    """
    PyDriller SZZ implementation.

    Spadini, D., Aniche, M., & Bacchelli, A. (2018, October). Pydriller: Python framework for mining software repositories.
    In Proceedings of the 2018 26th ACM Joint Meeting on European Software Engineering Conference and Symposium on the
    Foundations of Software Engineering (pp. 908-911).

    Supported **kwargs:
        * issue_date_filter: bool, default: False
        * issue_date: int
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

        # PyDriller-specific: only supports commit-based analysis; for unidiff, fallback to blame like BaseSZZ
        if unidiff_file_path:
            if impacted_files is None:
                impacted_files = self.get_impacted_files(unidiff_file_path=unidiff_file_path,
                                                         file_ext_to_parse=kwargs.get('file_ext_to_parse'),
                                                         only_deleted_lines=True)
            bug_introd_commits = set()
            for imp_file in impacted_files:
                # ensure the rev includes the file path
                rev_for_file = 'HEAD'
                if not self._path_exists_in_rev(rev_for_file, imp_file.file_path):
                    fallback_rev = self._last_rev_with_path('HEAD', imp_file.file_path)
                    rev_for_file = fallback_rev if fallback_rev else 'HEAD'

                blame_data = self._blame(
                    rev=rev_for_file,
                    file_path=imp_file.file_path,
                    modified_lines=imp_file.modified_lines,
                    ignore_whitespaces=False,
                    skip_comments=False
                )
                bug_introd_commits.update([entry.commit for entry in blame_data])

            if kwargs.get('issue_date_filter', False):
                bug_introd_commits = filter_by_date(bug_introd_commits, kwargs['issue_date'])
            else:
                log.info("Not filtering by issue date.")
            return bug_introd_commits

        self._set_working_tree_to_commit(fix_commit_hash)

        bug_introd_commits = set()

        gr = GitRepository(self.repository_path)
        pydriller_fix_commit = gr.get_commit(fix_commit_hash)
        for mod in pydriller_fix_commit.modifications:
            if match_files(mod.new_path, impacted_files) or match_files(mod.old_path, impacted_files):
                bics_per_mod = gr.get_commits_last_modified_lines(pydriller_fix_commit, mod)
                for bic_path, bic_commit_hashes in bics_per_mod.items():
                    for bic_commit_hash in bic_commit_hashes:
                        commit_introducing = self.get_commit(bic_commit_hash)
                        bug_introd_commits.add(commit_introducing)

        if kwargs.get('issue_date_filter', False):
            bug_introd_commits = filter_by_date(bug_introd_commits, kwargs['issue_date'])
        else:
            log.info("Not filtering by issue date.")

        return bug_introd_commits
