import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._

val spark = SparkSession.builder.appName("Recursive Query in Spark").getOrCreate()

// Step 1: Select second_resource_id to get distinct values
val secondResourceIds = catalog_relationship.select(col("second_resource_id")).distinct()

// Step 2: Perform a LEFT ANTI join to filter out matching rows (finding top-level parents)
val getTopLevelParent = catalog_relationship
  .select(
    col("first_resource_id").alias("destination"),
    lit(null).cast("string").alias("source"),  // Initially, source is null
    col("first_resource_id").alias("root")     // Root is initialized to itself
  )
  .join(secondResourceIds, col("destination") === col("second_resource_id"), "left")
  .filter(col("second_resource_id").isNull)   // This is equivalent to LEFT ANTI join logic
  .drop("second_resource_id")                 // Drop unwanted column

// Step 3: Recursively build the hierarchy
var resultDf = getTopLevelParent

// Loop to recursively find parent-child relationships until no new records are added
var updatedDf = getTopLevelParent
do {
  resultDf = updatedDf

  updatedDf = catalog_relationship
    .join(resultDf, catalog_relationship("second_resource_id") === resultDf("destination"), "inner")
    .select(
      col("first_resource_id").alias("destination"),
      col("second_resource_id").alias("source"),
      resultDf("root")
    )
    .union(resultDf)  // Add new parent-child mappings and retain previous mappings
    .distinct()       // Ensure no duplicates

} while (updatedDf.count() > resultDf.count())

// Step 4: Print the final result and row counts
println("Final Top Level ES count: " + updatedDf.count())
updatedDf.show()
