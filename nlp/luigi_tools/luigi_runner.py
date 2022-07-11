from subprocess import call

#from luigi import worker, rpc
import requests
import time
import threading

from data_access import *
from luigi_tools.phenotype_helper import *
from claritynlp_logging import log, ERROR
from luigi_module import PhenotypeTask
import luigi

import util
import threading
import multiprocessing
from queue import Queue, Empty

# get the number of CPU cores and use it to constrain the number of worker threads
_cpu_count = multiprocessing.cpu_count()

# user-specified number of workers
_luigi_workers = int(util.luigi_workers)

if _luigi_workers > 0 and _luigi_workers <= _cpu_count:
    # user specified a valid number of worker threads
    _worker_count = _luigi_workers
else:
    if _cpu_count >= 4:
        _worker_count = _cpu_count // 2
    else:
        _worker_count = _cpu_count - 1

# special token for terminating worker threads
_TERMINATE_WORKERS = None

log('luigi_runner: {0} CPUs, {1} workers'.format(_cpu_count, _worker_count))

# function to execute the phenotype tasks
def _worker(queue, worker_id):
    """
    Continually check the queue for work items; terminate if None appears.
    Work items must implement a run() function.
    """
    
    log('luigi_runner: worker {0} running...'.format(worker_id))
    while True:
        try:
            item = queue.get(timeout = 2)
        except Empty:
            # haven't seen the termination signal yet
            continue
        if item is _TERMINATE_WORKERS:
            # replace so that other workers will know to terminate
            queue.put(item)
            # now exit this worker thread
            break
        else:
            # run it
            item.run()
    log('luigi_runner: worker {0} exiting...'.format(worker_id))

# work queue for the worker threads
_queue = Queue()
# create and start the worker threads, which block until work items appear on the queue
_workers = [threading.Thread(target=_worker, args=(_queue, i)) for i in range(_worker_count)]
for worker in _workers:
    worker.start()


def shutdown_workers():
    # the thread termination command is the appearance of _TERMINATE_WORKERS on the queue
    _queue.put(_TERMINATE_WORKERS)
    for worker in _workers:
        worker.join()



#scheduler = rpc.RemoteScheduler(url=util.luigi_scheduler)


# def get_active_workers():
#     url = util.luigi_scheduler + "/api/task_list?data={%22status%22:%22RUNNING%22}"
#     log(url)
#     req = requests.get(url)
#     if req.status_code == 200:
#         json_res = req.json()
#         keys = (json_res['response'].keys())
#         return len(keys)

#     return 0


def run_pipeline(pipeline_type: str, pipeline_id: str, job_id: int, owner: str):
    log("PLEASE RUN PIPELINE THROUGH PHENOTYPES", ERROR)
    # active = get_active_workers()
    # total = int(util.luigi_workers)
    # while active >= total:
    #     time.sleep(10)
    #     active = get_active_workers()
    #
    # luigi_log = (util.log_dir + '/luigi_%s.log') % (str(job_id))
    #
    # scheduler_ = util.luigi_scheduler
    # log("running job %s on pipeline %s; logging here %s" % (str(job_id), str(pipeline_id), luigi_log))
    # func = "PYTHONPATH='.' luigi --workers %s --module luigi_module %s  --pipeline %s --job %s --owner %s " \
    #        "--pipelinetype %s --scheduler-url %s > %s 2>&1 &" % (str(util.luigi_workers), "PipelineTask", pipeline_id,
    #                                                              str(job_id), owner, pipeline_type, scheduler_,
    #                                                              luigi_log)
    # try:
    #     call(func, shell=True)
    # except Exception as ex:
    #     log(ex, file=sys.stderr)
    #     log("unable to execute %s" % func, file=sys.stderr)


def run_task(task):
    # worker_num = int(util.luigi_workers)
    # # multiprocess = worker_num > 1

    # w = worker.Worker(scheduler=scheduler, no_install_shutdown_handler=True, worker_processes=worker_num)
    # w.add(task, multiprocess=True, processes=2)
    # w.run()
    task.run()


def threaded_func(arg0, arg1, arg2):
    # time.sleep(2)
    # active = get_active_workers() * 3
    # log("{}=MAX LUIGI WORKERS".format(util.luigi_workers))
    # num_workers = int(util.luigi_workers)
    # n = 0
    # if active > num_workers:
    #     while active > num_workers and n < 30:
    #         log("{}=ACTIVE LUIGI WORKERS; SLEEPING..".format(active))
    #         time.sleep(5)
    #         active = get_active_workers()
    #         n += 1

    log("running job %s on phenotype %s" % (str(arg0), str(arg2)))
    task = PhenotypeTask(job=arg0, owner=arg1, phenotype=arg2)
    run_task(task)


def threaded_phenotype_task(job_id, owner, phenotype_id):
    thread = threading.Thread(target=threaded_func, args=(job_id, owner, phenotype_id))
    thread.start()


def run_phenotype_job(phenotype_id: str, job_id: str, owner: str):
    try:
        #threaded_phenotype_task(job_id, owner, phenotype_id)
        
        task = PhenotypeTask(job=job_id, phenotype=phenotype_id, owner=owner)
        #task.run()
        _queue.put(task)
    except Exception as ex:
        log(ex, file=sys.stderr, level=ERROR)
        log("unable to execute python task", file=sys.stderr, level=ERROR)


def run_phenotype(phenotype_model: PhenotypeModel, phenotype_id: str, job_id: int, background=True):
    pipelines = get_pipelines_from_phenotype(phenotype_model)
    pipeline_ids = []
    if pipelines and len(pipelines) > 0:
        for pipeline in pipelines:
            pipeline_id = insert_pipeline_config(pipeline, util.conn_string)
            insert_phenotype_mapping(phenotype_id, pipeline_id, util.conn_string)
            pipeline_ids.append(pipeline_id)

        run_phenotype_job(phenotype_id, str(job_id), phenotype_model.owner)
    return pipeline_ids


def run_ner_pipeline(pipeline_id, job_id, owner):
    # luigi.run(['PipelineTask', '--pipeline', pipeline_id, '--job', str(job_id), '--owner', owner, '--pipelinetype',
    #            'TermFinder'])
    log("PLEASE RUN PIPELINE THROUGH PHENOTYPES", ERROR)


def run_provider_assertion_pipeline(pipeline_id, job_id, owner):
    # luigi.run(['PipelineTask', '--pipeline', pipeline_id, '--job', str(job_id), '--owner', owner, '--pipelinetype',
    #            'ProviderAssertion'])
    log("PLEASE RUN PIPELINE THROUGH PHENOTYPES", ERROR)


def run_value_extraction_pipeline(pipeline_id, job_id, owner):
    # luigi.run(['PipelineTask', '--pipeline', pipeline_id, '--job', str(job_id), '--owner', owner, '--pipelinetype',
    #            'ValueExtractor'])
    log("PLEASE RUN PIPELINE THROUGH PHENOTYPES", ERROR)


if __name__ == "__main__":
    log("luigi running", DEBUG)
    # test_model = get_sample_phenotype()
    # test_model.debug = True
    # p_id = insert_phenotype_model(test_model, util.conn_string)
    # the_job_id = jobs.create_new_job(jobs.NlpJob(job_id=-1, name="Test Phenotype", description=test_model.description,
    #                                              owner=test_model.owner, status=jobs.STARTED, date_ended=None,
    #                                              phenotype_id=p_id, pipeline_id=-1,
    #                                              date_started=datetime.datetime.now(),
    #                                              job_type='PHENOTYPE'), util.conn_string)
    #
    # run_phenotype(test_model, p_id, the_job_id)
