#SPDX-License-Identifier: MIT
import logging, os, sys, time, requests, json
from datetime import datetime
from multiprocessing import Process, Queue
import pandas as pd
import sqlalchemy as s
from workers.worker_base import Worker

class ContributorBreadthWorker(Worker):
    def __init__(self, config={}):
        
        # Define the worker's type, which will be used for self identification.
        #   Should be unique among all workers and is the same key used to define 
        #   this worker's settings in the configuration file.
        worker_type = "contributor_breadth_worker"

        # Define what this worker can be given and know how to interpret
        # given is usually either [['github_url']] or [['git_url']] (depending if your 
        # worker is exclusive to repos that are on the GitHub platform)
        given = [['github_url']]

        # The name the housekeeper/broker use to distinguish the data model this worker can fill
        #   You will also need to name the method that does the collection for this model
        #   in the format *model name*_model() such as fake_data_model() for example
        models = ['contributor_breadth']

        # Define the tables needed to insert, update, or delete on
        #   The Worker class will set each table you define here as an attribute
        #   so you can reference all of them like self.message_table or self.repo_table
        data_tables = ['contributor_repo']
        # For most workers you will only need the worker_history and worker_job tables
        #   from the operations schema, these tables are to log worker task histories
        operations_tables = ['worker_history', 'worker_job']

        # If you need to do some preliminary interactions with the database, these MUST go
        # in the model method. The database connection is instantiated only inside of each 
        # data collection process

        # Run the general worker initialization
        super().__init__(worker_type, config, given, models, data_tables, operations_tables)

        # Define data collection info
        self.tool_source = 'Contributor Breadth Worker'
        self.tool_version = '0.0.0'
        self.data_source = 'GitHub API'

        # Do any additional configuration after the general initialization has been run
        self.config.update(config)



    def contributor_breadth_model(self, task, repo_id):
        """ This is just an example of a data collection method. All data collection 
            methods for all workers currently accept this format of parameters. If you 
            want to change these parameters, you can re-define the collect() method to 
            overwrite the Worker class' version of it (which is the method that calls
            this method).

            :param task: the task generated by the housekeeper and sent to the broker which 
            was then sent to this worker. Takes the example dict format of:
                {
                    'job_type': 'MAINTAIN', 
                    'models': ['fake_data'], 
                    'display_name': 'fake_data model for url: https://github.com/vmware/vivace',
                    'given': {
                        'git_url': 'https://github.com/vmware/vivace'
                    }
                }
            :param repo_id: the collect() method queries the repo_id given the git/github url
            and passes it along to make things easier. An int such as: 27869

        """

        self.logger.info("Starting contributor_breadth_model")

        cntrb_login_query = s.sql.text("""
            SELECT DISTINCT gh_login, cntrb_id 
            FROM augur_data.contributors 
            WHERE gh_login IS NOT NULL
        """)

        cntrb_logins = json.loads(pd.read_sql(cntrb_login_query, self.db, \
            params={}).to_json(orient="records"))

        self.logger.info("Finished collecting cntrbs that need collection. Count: {}".format(len(cntrb_logins)))

        action_map = {
            'insert': {
                'source': ['id'],
                'augur': ['event_id']
            }
        }

        for cntrb in cntrb_logins:

            self.logger.info("Cntrb record: {}".format(cntrb))

            repo_cntrb_url = f"https://api.github.com/users/{cntrb['gh_login']}/events"

            source_cntrb_repos = self.paginate_endpoint(repo_cntrb_url, action_map=action_map,
                 table=self.contributor_repo_table)

            self.logger.info("Length of data to be inserted: {}".format(len(source_cntrb_repos['insert'])))

            if len(source_cntrb_repos['all']) == 0:
                self.logger.info("There are no issues for this repository.\n")
                self.register_task_completion(task, repo_id, 'contributor_breadth')

            cntrb_repos_insert = [
                {
                    "cntrb_id": cntrb['cntrb_id'],
                    "repo_git": cntrb_repo['repo']['url'],
                    "tool_source": self.tool_source,
                    "tool_version": self.tool_version,
                    "data_source": self.data_source,
                    "repo_name": cntrb_repo['repo']['name'],
                    "gh_repo_id": cntrb_repo['repo']['id'],
                    "cntrb_category": cntrb_repo['type'],
                    "event_id": cntrb_repo['id']
                } for cntrb_repo in source_cntrb_repos['insert']
            ]

            self.logger.info("Length of cntrb_repos_insert: {}".format(len(cntrb_repos_insert)))


            if len(source_cntrb_repos['insert']) > 0:

                cntrb_repo_insert_result, cntrb_repo_update_result = self.bulk_insert(self.contributor_repo_table,
                     unique_columns=action_map['insert']['augur'], insert=cntrb_repos_insert)

                # id
                # type
                # repo.id 
                # repo.name 
                # repo.url 
                # created_at 

        #hit user endpoint, to get json that contains other endpoints to hit
        #then hit those endpoints
        #find repos, cntrb_category, then check if the row is already present

        # Any initial database instructions, like finding the last tuple inserted or generate the next ID value

        # Collection and insertion of data happens here

        # ...

        # Register this task as completed.
        #   This is a method of the worker class that is required to be called upon completion
        #   of any data collection model, this lets the broker know that this worker is ready
        #   for another task
        self.register_task_completion(task, None, 'contributor_breadth')

