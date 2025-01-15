import os
import csv
import time
from paperswithcode import PapersWithCodeClient
from scholarly import scholarly, ProxyGenerator
from typing import Optional

# キャッシュを有効化
pg = ProxyGenerator()
pg.FreeProxies() #.Cache()
scholarly.use_proxy(pg)

# タスクIDの取得（'3d-object-detection'は仮のIDです。実際のIDを確認してください）
# task_id = '3d-object-detection'
# dataset_id  = 'nuscenes'
# metric_name = 'NDS'
# APIトークン（必要に応じて設定）
API_TOKEN = '0909acbe65c81aaef99478e9197aa4b7cb2d2992' #'your_paperswithcode_api_token'


task_list = [
    ['3d-object-detection'          ,'nuscenes'     ,'NDS'],
    ['3d-object-detection'          ,'ScanNetV2'    ,'mAP'],
    ['3d-object-detection'          ,'SUN-RGBD val' ,'mAP'],
    ['3d-point-cloud-classification','modelnet40'   ,'Overrall-Accuracy'],
    ['3d-point-cloud-classification','scanobjectnN' ,'NDS'],
    ['semantic-segmentation'        ,'S3DIS Area5'  ,'mIoU'],
    ['semantic-segmentation'        ,'S3DIS'        ,'Mean IoU'],
    ['semantic-segmentation'        ,'ScanNet'      ,'mIoU'],
    ['semantic-segmentation'        ,'SUN-RGBD'     ,'Mean IoU'],
    ['semantic-segmentation'        ,'Semantic3D'   ,'mIoU'],
    ['3d-semantic-segmentation'     ,'SemanticKITTI','mIoU'],
    ['3d-semantic-segmentation'     ,'Toronto-3D'   ,'mIoU'],
    ['3d-semantic-segmentation'     ,'KITTI-360'    ,'mIoU'],
    ['lidar-semantic-segmentation'  ,'nuScenes'     ,'mIoU'],
    ['lidar-semantic-segmentation'  ,'Paris-Lille-3D','mIoU'],
    ['lidar-instance-segmentation'  ,'PScanNetV2'   ,'mAP'],
    ['multi-object-tracking'        ,'KITTI Test'   ,'HOTA'],
    ['3d-multi-object-tracking'     ,'nuScenes'     ,'AMOTA'],
    ['3d-multi-object-tracking'     ,'Waymo Open Dataset','MOTA'],
    ['visual-localization'          ,'Oxford Radar RobotCar','mt'],
    ['point-cloud-registration'     ,'ETH'          ,'Feature Matching Recall'],
    ['point-cloud-registration'     ,'3DMatch Benchmark','Feature Matching Recall'],
    ['point-cloud-registration'     ,'KITTI'        ,'Success Rate'],
    ['scene-Flow-estimation'        ,'Spring'       ,'1px total'],
    ['monocular-depth-estimation'   ,'NYU-Depth V2' ,'absolute relative error'],
    ['monocular-depth-estimation'   ,'KITTI Eigen split' ,'absolute relative error'],
    ['monocular-depth-estimation'   ,'KITTI Eigen split unsupervised' ,'absolute relative error'],
    ['monocular-depth-estimation'   ,'KITTI Eigen split unsupervised' ,'absolute relative error'],
    ['3D Semantic Scene Completion' ,'NYUv2'        ,'mIoU'],
    ['3D Semantic Scene Completion' ,'SemanticKITTI','mIoU'],
    ['3D Semantic Scene Completion' ,'KITTI-360'    ,'mIoU'],
    ['novel-view-synthesis'         ,'LLFF'         ,'PSNR'],
    ['novel-view-synthesis'         ,'NeRF'         ,'PSNR'],
    ['generalizable-novel-view-synthesis' ,'ZJU-MoCap'    ,'PSNR']
]

def main():
    # PapersWithCode クライアントの初期化
    client = PapersWithCodeClient(token=API_TOKEN)

    for task_id, dataset_id, metric_name in task_list:
        output_csv(client, task_id, dataset_id, metric_name)
        # Google ScholarおよびPapersWithCodeへのリクエスト間隔を設定（例: 5秒）
        time.sleep(5)

    print("すべての論文の処理が完了しました。")


def output_csv(client, task_id, dataset_id, metric_name):
    # タスクに関連する論文のリストを取得
    papers = get_task_paper_results(client, task_id=task_id)
    dataset_eval_list = client.dataset_evaluation_list(dataset_id)


    evaluation_id = "not_found"
    for result in dataset_eval_list.results:
        if result.dataset==dataset_id and result.task==task_id:
            evaluation_id = result.id
            break

    metric_list = client.evaluation_metric_list(evaluation_id=evaluation_id)
    print(f"------ task = {task_id}, dataset = {dataset_id} ------ metric list")
    for metric in metric_list.results:
        print(f"{metric.name}")

    output_dir = "results"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    # CSVファイル名の設定
    csv_filename = f"{evaluation_id}_citations_accuracy.csv"
    csv_path = os.path.join(output_dir, csv_filename)

    # 論文の結果リストを取得
    eval_results = get_evaluate_results(client, evaluation_id)
    print(f"取得したresultsの件数: {len(eval_results)}")

    # 既に処理済みの論文タイトルを保持するセット
    processed_data = dict()
    # CSVファイルが存在する場合、既存のタイトルを読み込む
    if os.path.exists(csv_path):
        with open(csv_path, mode='r', encoding='utf-8', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                lst = list(row.values())
                processed_data[lst[0]] = lst

    # CSVファイルが存在しない場合、ヘッダーを書き込む
    csv_file_exists = len(processed_data) > 0  # os.path.exists(csv_path)
    #mode = 'a' if csv_file_exists else 'w'
    with open(csv_path, mode='w', encoding='utf-8', newline='') as csvfile:
        fieldnames = ['methodology', 'title', 'citations', 'accuracy', 'date', 'proceeding', 'metric']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        best_metric = None

        for result in eval_results:            
            methodology = result.methodology
            #paper_id = paper.id

            paper_title = None
            accuracy = None
            evaluated_on = None
            citations= None
            proceeding = None
            if methodology in processed_data:
                row = processed_data[methodology]
                citations = row[2]
                # if row['title'] != None:
                #     paper_title = row['title']
                # if row['citations'].isascii():
                #     citations = int(row["citations"])
                # if row['accuracy'].isascii():
                #     accuracy = row['accuracy']
                # evaluated_on = row['date']
                # if row['proceeding']!= None:
                #     proceeding = row['proceeding']
                # if row['metric']!= None:
                #     best_metric = row['metric']                  

            print(f"処理中: {methodology}")

            # 精度のメトリックを取得（例: mAP）
            for paper in papers:            
                if paper.title:
                    if result.paper == paper.id:
                        paper_title = paper.title
                        proceeding = paper.proceeding
                        break
                    if paper.title.find(methodology) != -1:
                        paper_title = paper.title
                        proceeding = paper.proceeding                        
                        break                    

            # 引用数の取得
            if citations is None or citations=='エラー':
                try:
                    keyword = paper_title if paper_title is not None else methodology
                    search_query = scholarly.search_pubs(keyword)
                    paper_scholarly = next(search_query, None)
                    if paper_scholarly:
                        citations = paper_scholarly.get('num_citations', '引用数情報なし')
                    else:
                        citations = '引用情報が見つかりません'
                except Exception as e:
                    print(f"引用数の取得中にエラーが発生しました: {e}")
                    citations = 'エラー'

            # 精度の取得（nuScenesデータセット）
            #while True:
            try:
                # ここでは主要メトリックの値を取得する例
                if result.best_metric:
                    best_metric = result.best_metric 
                if best_metric:
                    accuracy = result.metrics[best_metric]
                if result.evaluated_on:
                    evaluated_on = result.evaluated_on

                # 結果の表示
                print(f"論文通称: {methodology}")
                print(f"論文タイトル: {paper_title}")
                print(f"引用数: {citations}")
                print(f"評価日: {evaluated_on}")
                print(f"精度: {accuracy}")
                print('-' * 40)

                # 結果をCSVに書き込む
                #writer.writerow({'title': title, 'citations': citations, 'accuracy{}': accuracy})
                writer.writerow({'methodology': methodology, 'title': paper_title, 'citations': citations, 'accuracy': accuracy, 'date': evaluated_on, 'proceeding': proceeding ,'metric': best_metric})
                csvfile.flush()  # データを即時に書き込む
                time.sleep(1.5)
                            
            except Exception as e:
                print(f"精度の取得中にエラーが発生しました: {e}")

def get_evaluate_results(client, evaluation_id):
    all_results = []
    page = 1
    items_per_page = 200  # デフォルト値

    _page = client.evaluation_result_list(
        evaluation_id=evaluation_id,
        page=page,
        items_per_page=items_per_page
    ) 

    _count = _page.count
   
    while len(all_results) < _count:
        try:
            _page = client.evaluation_result_list(
                evaluation_id=evaluation_id,
                page=page,
                items_per_page=items_per_page
            ) 
            
            if not _page.results:
                break
        except:
             break
        
        all_results.extend(_page.results)
        page += 1
        time.sleep(1.5)
        
    return all_results

def get_task_paper_results(client, task_id):
    all_results = []
    page = 1
    items_per_page = 200  # デフォルト値

    _page = client.task_paper_list(
        task_id=task_id,
        page=page,
        items_per_page=items_per_page
    ) 

    _count = _page.count
   
    while len(all_results) < _count:
        try:
            _page = client.task_paper_list(
                task_id=task_id,
                page=page,
                items_per_page=items_per_page
            ) 
            
            if not _page.results:
                break
        except:
             break
        all_results.extend(_page.results)
        page += 1
        time.sleep(1.5)
    
    return all_results


if __name__ == "__main__":
    main()